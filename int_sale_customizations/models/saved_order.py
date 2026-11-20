from odoo import fields, models


class SavedOrder(models.Model):
    _name = "int.saved.order"
    _description = "Saved order name"
    _order = "id desc"

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    order_id = fields.Many2one("sale.order", required=True, ondelete="cascade", index=True)
    name = fields.Char(required=True)

    _user_order_uniq = models.Constraint(
        "UNIQUE(user_id, order_id)",
        "This order already has a saved name for this person.",
    )
