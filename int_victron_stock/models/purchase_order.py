import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ACTIVITY_SUMMARY = "Finish PO and send to Victron"


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    int_victron_rfq = fields.Boolean(
        string="Victron Shortfall",
        copy=False,
        index=True,
        help="Drafted automatically for the part of a sales order the warehouse could not fill.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        self.env["product.template"]._int_victron_clear_po_cache()
        return orders

    def write(self, vals):
        result = super().write(vals)
        if {"state", "int_victron_rfq", "partner_id"} & set(vals):
            self.env["product.template"]._int_victron_clear_po_cache()
        return result

    def _int_victron_schedule_activity(self, user):
        """One open to-do per RFQ. A finished to-do is reopened when new lines arrive."""
        if not user:
            _logger.warning("Victron RFQ %s has no buyer; no activity was scheduled.", self.mapped("name"))
            return
        summary = self.env._(ACTIVITY_SUMMARY)
        note = self.env._(
            "Review the quantities and price, confirm Victron can still fill this, "
            "then confirm the purchase order. Nothing has been sent to Victron."
        )
        for order in self:
            order.user_id = user
            open_activity = order.activity_ids.filtered(
                lambda activity: activity.user_id == user and activity.summary == summary
            )
            if open_activity:
                continue
            order.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=note,
                user_id=user.id,
            )

    @api.model
    def _int_victron_add_shortfalls(self, plan):
        """Add ``plan`` (sale line id, quantity) onto a draft Victron RFQ.

        Lines from several sales orders share one draft until someone confirms it.
        Confirming the RFQ is the manual check before anything is ordered.
        """
        if not plan:
            return self.browse()
        vendor, buyer = self.env["sale.order"]._int_victron_parties()
        lines = self.env["sale.order.line"].browse([line_id for line_id, _qty in plan]).exists()
        if not vendor:
            _logger.warning(
                "Victron RFQ skipped for %s: set the vendor under Inventory → Settings → Victron E-Order.",
                lines.order_id.mapped("name"),
            )
            for order in lines.order_id:
                order.message_post(
                    body=order.env._(
                        "Units that Victron has to supply were not put on a purchase order. "
                        "Set the Victron vendor under Inventory → Settings → Victron E-Order."
                    ),
                    subtype_xmlid="mail.mt_note",
                )
            return self.browse()

        qty_by_line = dict(plan)
        created = self.browse()
        touched = self.browse()
        for company in lines.company_id:
            company_lines = lines.filtered(lambda line: line.company_id == company)
            domain = [
                ("int_victron_rfq", "=", True),
                ("state", "=", "draft"),
                ("partner_id", "=", vendor.id),
                ("company_id", "=", company.id),
            ]
            if buyer:
                domain.append(("user_id", "=", buyer.id))
            po = self.search(domain, limit=1, order="id desc")
            if not po:
                warehouse = company_lines.order_id.warehouse_id[:1] or self.env["stock.warehouse"].search(
                    [("company_id", "=", company.id)], limit=1
                )
                po = self.with_company(company).create({
                    "partner_id": vendor.id,
                    "company_id": company.id,
                    "user_id": buyer.id if buyer else False,
                    "int_victron_rfq": True,
                    "origin": ", ".join(company_lines.order_id.mapped("name")),
                    "picking_type_id": warehouse.in_type_id.id,
                })
                created |= po
            touched |= po
            origins = set(filter(None, (po.origin or "").split(", ")))
            for line in company_lines:
                qty = qty_by_line.get(line.id) or 0.0
                if qty <= 0:
                    continue
                existing = po.order_line.filtered(
                    lambda item: item.int_source_sale_line_id == line and not item.display_type
                )
                if existing:
                    existing.product_qty += qty
                else:
                    self.env["purchase.order.line"].create({
                        "order_id": po.id,
                        "product_id": line.product_id.id,
                        "product_qty": qty,
                        "product_uom_id": line.product_id.uom_id.id,
                        "int_source_sale_line_id": line.id,
                    })
                origins.add(line.order_id.name)
            po.origin = ", ".join(sorted(origins))
        self.env["product.template"]._int_victron_clear_po_cache()
        touched._int_victron_schedule_activity(buyer)
        _logger.info(
            "Victron RFQ %s updated for %s.",
            touched.mapped("name"),
            lines.order_id.mapped("name"),
        )
        return created or touched

    @api.model
    def _int_victron_on_sale_cancel(self, orders):
        """Drop draft lines that belonged to a cancelled sale. Leave a confirmed PO alone."""
        sources = orders.order_line
        if not sources:
            return
        lines = self.env["purchase.order.line"].search([
            ("int_source_sale_line_id", "in", sources.ids),
            ("order_id.int_victron_rfq", "=", True),
        ])
        draft_lines = lines.filtered(lambda line: line.order_id.state in ("draft", "sent"))
        confirmed = lines - draft_lines
        draft_orders = draft_lines.order_id
        draft_lines.unlink()
        empty = draft_orders.filtered(lambda order: not order.order_line)
        empty.unlink()
        for order in confirmed.order_id:
            order.message_post(
                body=order.env._(
                    "A sales order that this purchase was covering has been cancelled. "
                    "Review the quantities before sending it to Victron."
                ),
                subtype_xmlid="mail.mt_note",
            )
        self.env["product.template"]._int_victron_clear_po_cache()
        if draft_orders - empty:
            _buyer = draft_orders.user_id[:1]
            (draft_orders - empty)._int_victron_schedule_activity(_buyer)


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    int_source_sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Sales Order Line",
        copy=False,
        index=True,
        ondelete="set null",
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self.env["product.template"]._int_victron_clear_po_cache()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if {"product_qty", "qty_received", "product_id", "order_id"} & set(vals):
            self.env["product.template"]._int_victron_clear_po_cache()
        return result

    def unlink(self):
        result = super().unlink()
        self.env["product.template"]._int_victron_clear_po_cache()
        return result
