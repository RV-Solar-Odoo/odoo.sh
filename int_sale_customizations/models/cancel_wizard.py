from odoo import fields, models


class IntSaleCancelWizard(models.TransientModel):
    _name = "int.sale.cancel.wizard"
    _description = "Confirm or deny a cancellation request"

    order_id = fields.Many2one("sale.order", required=True)
    preference = fields.Selection(
        [
            ("store_credit", "Store credit"),
            ("original", "Original payment method"),
        ],
        string="Refund method",
        default="store_credit",
    )
    note = fields.Text(string="Note")

    def action_confirm(self):
        self.ensure_one()
        self.order_id.int_confirm_cancellation(self.env.user, self.preference, self.note)
        return {"type": "ir.actions.act_window_close"}

    def action_deny(self):
        self.ensure_one()
        self.order_id.int_deny_cancellation(self.env.user, self.note)
        return {"type": "ir.actions.act_window_close"}
