from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command

SAVED_NAME_LIMIT = 80


class ResUsers(models.Model):
    _inherit = "res.users"

    int_pinned_order_ids = fields.Many2many(
        "sale.order",
        "int_user_pinned_order_rel",
        "user_id",
        "order_id",
        string="Pinned orders",
    )

    def write(self, vals):
        if "int_pinned_order_ids" in vals and self.env.user.share and not self.env.su:
            raise AccessError(_("Pin orders from My Orders."))
        return super().write(vals)

    def int_portal_toggle_pin(self, order):
        """Pin or unpin one of this user's own orders. Returns 'pinned' or 'unpinned'."""
        self.ensure_one()
        order.ensure_one()
        if not self.int_portal_can("pin_orders") or not order._int_owned_by(self):
            raise UserError(_("You cannot pin this order."))
        if order in self.int_pinned_order_ids:
            self.sudo().write({"int_pinned_order_ids": [Command.unlink(order.id)]})
            self.env["int.saved.order"].sudo().search([
                ("user_id", "=", self.id),
                ("order_id", "=", order.id),
            ]).unlink()
            return "unpinned"
        limit = self._int_pin_limit()
        if len(self.int_pinned_order_ids) >= limit:
            raise UserError(_("You can pin up to %(limit)s orders. Unpin one first.", limit=limit))
        self.sudo().write({"int_pinned_order_ids": [Command.link(order.id)]})
        return "pinned"

    def int_portal_name_saved_order(self, order, name):
        """Set or clear the name this user sees for a pinned order."""
        self.ensure_one()
        order.ensure_one()
        if not self.int_portal_can("pin_orders") or not order._int_owned_by(self):
            raise UserError(_("You cannot name this order."))
        if order not in self.int_pinned_order_ids:
            raise UserError(_("Pin the order before naming it."))
        label = " ".join((name or "").split())[:SAVED_NAME_LIMIT]
        Saved = self.env["int.saved.order"].sudo()
        existing = Saved.search([
            ("user_id", "=", self.id),
            ("order_id", "=", order.id),
        ], limit=1)
        if not label:
            existing.unlink()
            return ""
        if existing:
            existing.name = label
        else:
            Saved.create({"user_id": self.id, "order_id": order.id, "name": label})
        return label

    def _int_portal_saved_names(self, orders):
        """Saved names for these orders, for the current user."""
        self.ensure_one()
        if not orders:
            return {}
        rows = self.env["int.saved.order"].sudo().search([
            ("user_id", "=", self.id),
            ("order_id", "in", orders.ids),
        ])
        return {row.order_id.id: row.name for row in rows}

    def _int_portal_saved_name(self, order):
        self.ensure_one()
        return self._int_portal_saved_names(order).get(order.id, "")

    def _int_portal_dashboard_tickets(self, commercial, company):
        """Open tickets first, then closed ones. Empty when helpdesk is absent."""
        if "helpdesk.ticket" not in self.env:
            return []
        Ticket = self.env["helpdesk.ticket"]
        domain = [
            ("partner_id", "child_of", commercial.id),
            ("company_id", "=", company.id),
        ]
        try:
            open_tickets = Ticket.search(
                domain + ["|", ("stage_id", "=", False), ("stage_id.fold", "=", False)],
                order="create_date desc, id desc",
                limit=5,
            )
            closed = Ticket.browse()
            if len(open_tickets) < 5:
                closed = Ticket.search(
                    domain + [("stage_id.fold", "=", True)],
                    order="create_date desc, id desc",
                    limit=5 - len(open_tickets),
                )
        except AccessError:
            return Ticket.browse()
        return open_tickets + closed

    def _int_pin_limit(self):
        self.ensure_one()
        company = self._int_portal_company() if hasattr(self, "_int_portal_company") else self.env.company
        return company.int_max_pinned or 5

    def _int_portal_store_credit(self):
        """Store credit balance, or False when this role should not see it.

        A configured program with no card yet is shown as zero.
        """
        self.ensure_one()
        if not self.int_portal_can("view_store_credit"):
            return False
        company = self._int_portal_company() if hasattr(self, "_int_portal_company") else self.env.company
        program = company.sudo().int_store_credit_program_id
        if not program:
            return False
        card = self.env["loyalty.card"].sudo().search([
            ("program_id", "=", program.id),
            ("partner_id", "=", self.partner_id.commercial_partner_id.id),
        ], limit=1)
        currency = program.currency_id or company.currency_id
        return {"amount": card.points if card else 0.0, "currency": currency}

    def _int_portal_dashboard(self):
        """Home-page lists for an approved dealer, or False for everyone else.

        Approved means the commercial partner's pricelist is not the public one.
        Invoice rows are read as this user, so a buyer or viewer gets none.
        """
        self.ensure_one()
        if self._is_public() or not self.has_group("base.group_portal"):
            return False
        company = self._int_portal_company() if hasattr(self, "_int_portal_company") else self.env.company
        if not self._int_portal_is_dealer(company):
            return False
        commercial = self.partner_id.commercial_partner_id
        SaleOrder = self.env["sale.order"]
        orders = SaleOrder.sudo().search(
            SaleOrder._int_portal_order_domain(commercial),
            order="date_order desc, id desc",
            limit=5,
        )
        Picking = self.env["stock.picking"]
        deliveries = Picking.sudo().search(
            Picking._int_portal_delivery_domain(commercial),
            order="scheduled_date desc, id desc",
            limit=5,
        )
        saved = self.int_pinned_order_ids.filtered(
            lambda order: order.partner_id.commercial_partner_id == commercial and order.state in ("sale", "cancel")
        )
        tickets = self._int_portal_dashboard_tickets(commercial, company)
        show_invoices = self.int_portal_can("view_invoices")
        invoices = to_pay = self.env["account.move"]
        if show_invoices:
            Move = self.env["account.move"]
            posted = [
                ("state", "=", "posted"),
                ("partner_id", "child_of", commercial.id),
                ("company_id", "=", company.id),
            ]
            invoices = Move.search(
                posted + [("move_type", "in", ("out_invoice", "out_refund"))],
                order="invoice_date desc, id desc",
                limit=5,
            )
            to_pay = Move.search(
                posted + [
                    ("move_type", "=", "out_invoice"),
                    ("payment_state", "in", ("not_paid", "partial")),
                    ("amount_residual", ">", 0),
                ],
                order="invoice_date_due asc, id asc",
                limit=8,
            )
        return {
            "orders": orders,
            "deliveries": deliveries,
            "saved": saved,
            "saved_names": self._int_portal_saved_names(saved),
            "tickets": tickets,
            "show_invoices": show_invoices,
            "invoices": invoices,
            "to_pay": to_pay,
        }
