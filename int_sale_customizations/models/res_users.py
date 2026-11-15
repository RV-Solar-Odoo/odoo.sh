from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

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
