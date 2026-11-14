from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command


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
            return "unpinned"
        limit = self._int_pin_limit()
        if len(self.int_pinned_order_ids) >= limit:
            raise UserError(_("You can pin up to %(limit)s orders. Unpin one first.", limit=limit))
        self.sudo().write({"int_pinned_order_ids": [Command.link(order.id)]})
        return "pinned"

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
