import csv
import io
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


CANCEL_REASONS = [
    ("no_longer_needed", "No longer needed"),
    ("ordered_wrong_item", "Ordered the wrong item"),
    ("found_elsewhere", "Found it elsewhere"),
    ("delay", "Delay"),
    ("other", "Other"),
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    int_cancel_state = fields.Selection(
        [
            ("none", "None"),
            ("requested", "Requested"),
            ("approved", "Approved"),
            ("denied", "Denied"),
        ],
        string="Cancellation",
        default="none",
        tracking=True,
        copy=False,
    )
    int_cancel_reason = fields.Selection(CANCEL_REASONS, string="Cancel reason", copy=False)
    int_cancel_note = fields.Text(string="Cancel note", copy=False)
    int_cancel_refund_pref = fields.Selection(
        [
            ("store_credit", "Store credit"),
            ("original", "Original payment method"),
        ],
        string="Refund preference",
        copy=False,
    )
    int_cancel_requested_by = fields.Many2one("res.users", copy=False)
    int_cancel_requested_on = fields.Datetime(copy=False)
    int_cancel_decided_by = fields.Many2one("res.users", copy=False)
    int_cancel_decision_note = fields.Text(copy=False)
    int_cancel_settled = fields.Boolean(copy=False)
    int_ship_location_type = fields.Selection(related="partner_shipping_id.int_location_type")
    int_ship_has_dock = fields.Boolean(related="partner_shipping_id.int_has_loading_dock")
    int_ship_has_forklift = fields.Boolean(related="partner_shipping_id.int_has_forklift")

    def _int_portal_shipments(self):
        """Tracking for each order, read from the pickings already on those orders.

        One pass over the outgoing shipments. Cancelled shipments are left out.
        ``partial`` is true when something has shipped and something is still open.
        """
        pickings = self.picking_ids.filtered(
            lambda picking: picking.picking_type_code == "outgoing" and picking.state != "cancel"
        )
        pickings.mapped("carrier_tracking_ref")
        pickings.mapped("carrier_tracking_url")
        pickings.mapped("carrier_id")
        grouped = {}
        for picking in pickings.sorted("id"):
            grouped.setdefault(picking.sale_id.id, []).append(picking)
        result = {}
        for order in self:
            rows = []
            links = []
            shipped = False
            still_open = False
            for picking in grouped.get(order.id, []):
                picking_links = picking._int_portal_tracking_links()
                done = picking.state == "done"
                if done:
                    shipped = True
                    links.extend(picking_links)
                else:
                    still_open = True
                rows.append({
                    "name": picking.name,
                    "done": done,
                    "links": picking_links,
                })
            result[order.id] = {
                "links": links,
                "partial": shipped and still_open,
                "shipments": rows,
            }
        return result

    def _int_owned_by(self, user):
        self.ensure_one()
        return self.partner_id.commercial_partner_id == user.partner_id.commercial_partner_id

    def _int_outgoing(self):
        self.ensure_one()
        return self.picking_ids.filtered(lambda picking: picking.picking_type_code == "outgoing")

    def _int_cancel_blocked_reason(self):
        """Why this order cannot be cancelled, or False when it can."""
        self.ensure_one()
        if self.state not in ("sale", "sent"):
            return _("Only a confirmed order can be cancelled.")
        outgoing = self._int_outgoing()
        if outgoing.filtered(lambda picking: picking.state == "done"):
            return _("A delivery has already shipped.")
        labeled = outgoing.filtered(
            lambda picking: picking.state not in ("cancel", "done") and picking.carrier_tracking_ref
        )
        if labeled:
            return _("A shipping label has already been created.")
        if self.int_cancel_state not in ("none", "denied"):
            return _("A cancellation request is already open.")
        return False

    def _int_cancel_needs_refund(self):
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda move: move.state == "posted" and move.move_type == "out_invoice"
        )
        return any(float_compare(invoice.amount_total, invoice.amount_residual, precision_rounding=invoice.currency_id.rounding) > 0 for invoice in invoices)

    @api.model
    def _int_portal_order_domain(self, commercial, search=None, search_in="all", filterby="all", date_begin=None, date_end=None):
        """Orders for one dealer, plus the portal search and status filters."""
        domain = [("partner_id", "child_of", commercial.id)]
        if filterby == "cancelled":
            domain.append(("state", "=", "cancel"))
        elif filterby == "cancel_requested":
            domain += [("state", "=", "sale"), ("int_cancel_state", "=", "requested")]
        elif filterby == "shipped":
            domain += [("state", "=", "sale"), ("delivery_status", "=", "full")]
        elif filterby == "open":
            domain += [("state", "=", "sale"), ("delivery_status", "in", (False, "pending", "started", "partial"))]
        elif filterby == "backordered":
            moves = self.env["stock.picking"]._int_portal_backorder_moves(commercial)
            domain += [("state", "=", "sale"), ("id", "in", moves.sale_line_id.order_id.ids)]
        else:
            domain.append(("state", "in", ("sale", "cancel")))
        if date_begin:
            domain.append(("date_order", ">=", fields.Datetime.to_datetime(date_begin)))
        if date_end:
            end = fields.Datetime.to_datetime(date_end) + timedelta(days=1)
            domain.append(("date_order", "<", end))
        term = (search or "").strip()
        if not term:
            return domain
        search_in = search_in or "all"
        pieces = []
        if search_in in ("all", "name"):
            pieces.append([("name", "ilike", term)])
        if search_in in ("all", "po"):
            pieces.append([("client_order_ref", "ilike", term)])
        if search_in in ("all", "ship"):
            pieces.append(["|", "|", "|",
                ("partner_shipping_id.name", "ilike", term),
                ("partner_shipping_id.street", "ilike", term),
                ("partner_shipping_id.city", "ilike", term),
                ("partner_shipping_id.zip", "ilike", term),
            ])
        if search_in in ("all", "product"):
            pieces.append(["|",
                ("order_line.product_id.default_code", "ilike", term),
                ("order_line.product_id.name", "ilike", term),
            ])
        if search_in in ("all", "serial"):
            pieces.append([("id", "in", self._int_serial_order_ids(commercial, term))])
        if not pieces:
            return domain + [("id", "=", 0)]
        if len(pieces) == 1:
            return domain + pieces[0]
        combined = []
        for extra in pieces:
            combined = (["|"] + combined + extra) if combined else extra
        return domain + combined

    @api.model
    def _int_portal_orders_page(self, domain, order, pinned_ids, limit, offset):
        """One page of the My Orders list, with pinned orders first.

        The chosen sort still applies inside the pinned rows and inside the rest.
        A pin that does not match ``domain`` stays off the page.
        """
        if not self.has_access("read"):
            return self.browse()
        pinned_ids = [order_id for order_id in pinned_ids if isinstance(order_id, int)]
        if not pinned_ids:
            return self.search(domain, order=order, limit=limit, offset=offset)
        pinned_count = self.search_count(domain + [("id", "in", pinned_ids)])
        others = domain + [("id", "not in", pinned_ids)]
        if offset >= pinned_count:
            return self.search(others, order=order, limit=limit, offset=offset - pinned_count)
        pinned = self.search(
            domain + [("id", "in", pinned_ids)],
            order=order,
            limit=min(limit, pinned_count - offset),
            offset=offset,
        )
        remaining = limit - len(pinned)
        if not remaining:
            return pinned
        return pinned + self.search(others, order=order, limit=remaining, offset=0)

    @api.model
    def _int_serial_order_ids(self, commercial, term):
        if not self._int_portal_commercial_allowed(commercial):
            return []
        lots = self.env["stock.lot"].sudo().search([("name", "ilike", term)])
        if not lots:
            return []
        pickings = self.env["stock.picking"].sudo().search([
            ("move_line_ids.lot_id", "in", lots.ids),
            ("sale_id.partner_id", "child_of", commercial.id),
            ("picking_type_code", "=", "outgoing"),
        ])
        return pickings.sale_id.ids

    def _int_portal_commercial_allowed(self, commercial):
        user = self.env.user
        if user._is_public():
            return False
        if user.share and commercial != user.partner_id.commercial_partner_id:
            return False
        return True

    @api.model
    def _int_product_on_website(self, product, website):
        template = product.product_tmpl_id
        if not product.active or not product.sale_ok:
            return False
        company = website.company_id if website else self.env.company
        if product.company_id and company and product.company_id != company:
            return False
        if "is_published" in template._fields and not template.is_published:
            return False
        return True

    def _int_reorder_plan(self, website):
        """Lines that can go back in the cart, and the ones to explain first."""
        self.ensure_one()
        addable = self.env["sale.order.line"]
        skipped = []
        for line in self.order_line:
            product = line.product_id
            if line.display_type or not product or getattr(line, "is_delivery", False):
                continue
            if self._int_product_on_website(product, website):
                addable |= line
            elif not product.active or not product.sale_ok:
                skipped.append((product.display_name, _("Not available")))
            elif "is_published" in product.product_tmpl_id._fields and not product.product_tmpl_id.is_published:
                skipped.append((product.display_name, _("Not published on the website")))
            else:
                skipped.append((product.display_name, _("Not available")))
        return addable, skipped

    def _int_export_rows(self):
        """One list per order line, in the portal export column order."""
        rows = []
        for order in self:
            shipments = order._int_portal_shipments().get(order.id, {})
            tracking = ", ".join(link["number"] for link in shipments.get("links") or [])
            ship = order.partner_shipping_id
            address = ", ".join(part for part in (
                ship.street, ship.street2, ship.city, ship.state_id.code, ship.zip, ship.country_id.code,
            ) if part)
            for line in order.order_line.filtered(lambda item: not item.display_type and item.product_id):
                serials = line.move_ids.move_line_ids.filtered(
                    lambda move_line: move_line.state == "done" and move_line.lot_id
                ).lot_id.mapped("name")
                rows.append([
                    order.name,
                    fields.Datetime.to_string(order.date_order),
                    order.client_order_ref or "",
                    order.state,
                    ship.name or "",
                    address,
                    line.product_id.default_code or "",
                    line.product_id.name or "",
                    line.product_uom_qty,
                    line.qty_delivered,
                    line.price_unit,
                    line.price_subtotal,
                    order.amount_total,
                    tracking,
                    ", ".join(serials),
                    ship.int_address_category or "",
                    ship.int_location_type or "",
                    "Yes" if ship.int_has_loading_dock else "No",
                    "Yes" if ship.int_has_forklift else "No",
                ])
        return rows

    @api.model
    def _int_export_header(self):
        return [
            "Order #", "Order date", "PO #", "Status", "Ship-to name", "Ship-to address",
            "SKU", "Product", "Qty ordered", "Qty delivered", "Unit price", "Line subtotal",
            "Order total", "Tracking #s", "Serial #s",
            "Category", "Commercial/Residential", "Dock", "Forklift",
        ]

    def int_portal_request_cancel(self, user, reason, note, preference):
        """Record a cancellation request. Does not cancel or refund the order."""
        self.ensure_one()
        if not user.int_portal_can("cancel_orders") or not self._int_owned_by(user):
            raise UserError(_("You cannot request cancellation on this order."))
        blocked = self._int_cancel_blocked_reason()
        if blocked:
            raise UserError(blocked)
        if reason not in dict(CANCEL_REASONS):
            raise UserError(_("Choose a reason."))
        needs_refund = self._int_cancel_needs_refund()
        if needs_refund and preference not in ("store_credit", "original"):
            raise UserError(_("Choose how the refund should be paid."))
        order = self.sudo()
        order.write({
            "int_cancel_state": "requested",
            "int_cancel_reason": reason,
            "int_cancel_note": note or False,
            "int_cancel_refund_pref": preference if needs_refund else False,
            "int_cancel_requested_by": user.id,
            "int_cancel_requested_on": fields.Datetime.now(),
            "int_cancel_decided_by": False,
            "int_cancel_decision_note": False,
        })
        order.message_post(body=_(
            "Cancellation requested. Nothing has been cancelled and nothing has been refunded."
        ))
        order._int_alert_cancel_request()

    def _int_alert_cancel_request(self):
        self.ensure_one()
        company = self.company_id
        users = company.int_cancel_notify_user_ids.filtered(lambda user: user.active and not user.share)
        if self.user_id and not self.user_id.share:
            users |= self.user_id
        commercial = self.partner_id.commercial_partner_id
        subject = _("Cancel request: %(order)s – %(dealer)s", order=self.name, dealer=commercial.name)
        body = _(
            "Order %(order)s is %(state)s. Deliveries: %(pickings)s. Payment: %(payment)s. "
            "Reason: %(reason)s.",
            order=self.name,
            state=self.state,
            pickings=", ".join(
                f"{picking.name} ({picking.state})" for picking in self._int_outgoing()
            ) or _("none"),
            payment=self.invoice_status or "",
            reason=dict(CANCEL_REASONS).get(self.int_cancel_reason, ""),
        )
        self.message_post(subject=subject, body=body, partner_ids=users.partner_id.ids)
        for user in users:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=subject,
                note=body,
                user_id=user.id,
            )

    def int_confirm_cancellation(self, staff, preference, note):
        """Staff approval. Re-checks shipping, then cancels and settles money once."""
        self.ensure_one()
        if not staff.has_group("sales_team.group_sale_manager"):
            raise UserError(_("Only a sales manager can confirm a cancellation."))
        self.env.cr.execute("SELECT int_cancel_state, int_cancel_settled FROM sale_order WHERE id = %s FOR UPDATE", [self.id])
        state, settled = self.env.cr.fetchone()
        if state == "approved" or settled:
            raise UserError(_("This cancellation was already confirmed."))
        if state != "requested":
            raise UserError(_("There is no open cancellation request."))
        self.invalidate_recordset(["int_cancel_state", "int_cancel_settled"])
        outgoing_done = self._int_outgoing().filtered(lambda picking: picking.state == "done")
        if outgoing_done:
            raise UserError(_("A delivery has shipped since the request. The cancellation was not confirmed."))
        chosen = preference or self.int_cancel_refund_pref or "store_credit"
        if chosen not in ("store_credit", "original"):
            chosen = "store_credit"
        paid, invoices = self._int_paid_invoices()
        notes = self.env["account.move"]
        if invoices and paid <= 0:
            notes = self._int_reverse_invoices(invoices)
        elif paid > 0 and chosen == "store_credit":
            self._int_require_store_credit()
            notes = self._int_reverse_invoices(invoices)
            self._int_issue_store_credit(paid, notes)
        elif paid > 0:
            notes = self._int_reverse_invoices(invoices)
            self._int_refund_original(paid, invoices)
        if self.state != "cancel":
            self._action_cancel()
        self.write({
            "int_cancel_state": "approved",
            "int_cancel_settled": True,
            "int_cancel_decided_by": staff.id,
            "int_cancel_decision_note": note or False,
            "int_cancel_refund_pref": chosen if paid > 0 else self.int_cancel_refund_pref,
        })
        self.message_post(body=_(
            "Cancellation confirmed. Refund method: %(method)s. Amount: %(amount)s.",
            method=chosen if paid > 0 else _("no refund, the order was not paid"),
            amount=paid,
        ))

    def action_int_open_cancel_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cancellation"),
            "res_model": "int.sale.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
                "default_preference": self.int_cancel_refund_pref or "store_credit",
            },
        }

    def int_deny_cancellation(self, staff, note):
        self.ensure_one()
        if not staff.has_group("sales_team.group_sale_manager"):
            raise UserError(_("Only a sales manager can deny a cancellation."))
        if self.int_cancel_state != "requested":
            raise UserError(_("There is no open cancellation request."))
        if not (note or "").strip():
            raise UserError(_("A note is required to deny the request."))
        self.write({
            "int_cancel_state": "denied",
            "int_cancel_decided_by": staff.id,
            "int_cancel_decision_note": note.strip(),
        })
        self.message_post(body=_("Cancellation denied. %(note)s", note=note.strip()))
        self.activity_ids.filtered(lambda activity: activity.user_id == staff).action_feedback(feedback=note.strip())

    def _int_paid_invoices(self):
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda move: move.state == "posted" and move.move_type == "out_invoice"
        )
        paid = 0.0
        for invoice in invoices:
            paid += invoice.amount_total - invoice.amount_residual
        return paid, invoices

    def _int_require_store_credit(self):
        company = self.company_id
        if not company.int_store_credit_program_id or not company.int_store_credit_product_id:
            raise UserError(_("Set the store credit program and top-up product on the company before confirming this refund."))

    def _int_reverse_invoices(self, invoices):
        reversal = self.env["account.move.reversal"].with_context(
            active_model="account.move",
            active_ids=invoices.ids,
        ).create({
            "reason": _("Cancellation %s", self.name),
        })
        reversal.reverse_moves()
        notes = reversal.new_move_ids
        drafts = notes.filtered(lambda move: move.state == "draft")
        if drafts:
            drafts.action_post()
        lines = (invoices | notes).line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable" and not line.reconciled
        )
        if lines.filtered("debit") and lines.filtered("credit"):
            lines.reconcile()
        return notes

    def _int_issue_store_credit(self, amount, notes):
        company = self.company_id
        product = company.int_store_credit_product_id
        program = company.int_store_credit_program_id
        commercial = self.partner_id.commercial_partner_id
        topup = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": commercial.id,
            "invoice_origin": self.name,
            "invoice_line_ids": [(0, 0, {
                "product_id": product.id,
                "quantity": 1,
                "price_unit": amount,
                "name": _("Store credit refund %s", self.name),
            })],
        })
        topup.action_post()
        receivable = (notes | topup).line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable" and not line.reconciled
        )
        if receivable:
            receivable.reconcile()
        card = self.env["loyalty.card"].search([
            ("program_id", "=", program.id),
            ("partner_id", "=", commercial.id),
        ], limit=1)
        if not card:
            card = self.env["loyalty.card"].create({
                "program_id": program.id,
                "partner_id": commercial.id,
            })
        card.points += amount
        self.env["loyalty.history"].create({
            "card_id": card.id,
            "description": _("Refund – %s", self.name),
            "issued": amount,
            "order_model": "sale.order",
            "order_id": self.id,
        })

    def _int_refund_original(self, amount, invoices):
        txs = self.env["payment.transaction"]
        if "transaction_ids" in invoices._fields:
            txs = invoices.transaction_ids.filtered(lambda tx: tx.state == "done")
        if not txs:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Refund %(order)s manually", order=self.name),
                note=_("The payment was not made through a refundable provider. Refund %(amount)s manually.", amount=amount),
                user_id=self.user_id.id or self.env.user.id,
            )
            return
        remaining = amount
        for tx in txs:
            if remaining <= 0:
                break
            chunk = min(remaining, tx.amount)
            tx.sudo().action_refund(amount_to_refund=chunk)
            remaining -= chunk

    @api.model
    def _int_po_rows_from_xlsx(self, raw):
        try:
            import openpyxl
        except ImportError as exc:
            raise UserError(_("The spreadsheet reader is not available.")) from exc
        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        sheet = workbook.active
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        return self._int_po_rows(rows)

    @api.model
    def _int_po_rows(self, rows):
        """Return (po_number, [(sku, qty), ...]) from a sheet of cell values."""
        po_number = ""
        header_index = None
        sku_col = qty_col = po_col = None
        for index, row in enumerate(rows[:8]):
            labels = [str(cell).strip().lower() if cell is not None else "" for cell in row]
            if "sku" in labels and "qty" in labels:
                header_index = index
                sku_col = labels.index("sku")
                qty_col = labels.index("qty")
                po_col = labels.index("po number") if "po number" in labels else None
                break
            for cell_index, label in enumerate(labels):
                if label == "po number" and cell_index + 1 < len(row) and row[cell_index + 1]:
                    po_number = str(row[cell_index + 1]).strip()
        if header_index is None:
            raise UserError(_("The spreadsheet needs a header row with SKU and Qty."))
        parsed = []
        for row in rows[header_index + 1:]:
            if not row or all(cell in (None, "") for cell in row):
                continue
            sku = str(row[sku_col]).strip() if sku_col < len(row) and row[sku_col] not in (None, "") else ""
            qty = row[qty_col] if qty_col < len(row) else None
            if po_col is not None and po_col < len(row) and row[po_col] and not po_number:
                po_number = str(row[po_col]).strip()
            parsed.append((sku, qty))
        if len(parsed) > 500:
            raise UserError(_("A purchase order upload can contain at most 500 rows."))
        return po_number, parsed

    def _int_match_po_rows(self, parsed, website):
        added = []
        rejected = []
        company = website.company_id if website else self.env.company
        for sku, qty in parsed:
            if not sku:
                rejected.append(("", _("The SKU is missing.")))
                continue
            try:
                quantity = int(qty)
            except (TypeError, ValueError):
                rejected.append((sku, _("Quantity must be a positive whole number.")))
                continue
            if quantity <= 0:
                rejected.append((sku, _("Quantity must be a positive whole number.")))
                continue
            products = self.env["product.product"].search([
                ("default_code", "=", sku),
                ("sale_ok", "=", True),
                "|", ("company_id", "=", False), ("company_id", "=", company.id),
            ]).filtered(lambda product: self._int_product_on_website(product, website))
            if not products:
                rejected.append((sku, _("Unknown SKU or not available.")))
            elif len(products) > 1:
                rejected.append((sku, _("More than one product uses this SKU.")))
            else:
                added.append((products, quantity))
        return added, rejected

    def _int_export_csv(self):
        buffer = io.StringIO()
        buffer.write("\ufeff")
        writer = csv.writer(buffer)
        writer.writerow(self._int_export_header())
        writer.writerows(self._int_export_rows())
        return buffer.getvalue().encode("utf-8")

    def _int_export_xlsx(self):
        import xlsxwriter
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        sheet = workbook.add_worksheet("Orders")
        for column, title in enumerate(self._int_export_header()):
            sheet.write(0, column, title)
        for row_index, row in enumerate(self._int_export_rows(), start=1):
            for column, value in enumerate(row):
                sheet.write(row_index, column, value)
        workbook.close()
        return buffer.getvalue()

    def _int_po_template_xlsx(self):
        import xlsxwriter
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        sheet = workbook.add_worksheet("PO")
        sheet.write(0, 0, "PO Number")
        sheet.write(2, 0, "SKU")
        sheet.write(2, 1, "Qty")
        workbook.close()
        return buffer.getvalue()
