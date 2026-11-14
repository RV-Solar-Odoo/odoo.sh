from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    int_max_pinned = fields.Integer(
        string="Pinned orders",
        default=5,
        help="How many orders one portal user can pin.",
    )
    int_store_credit_program_id = fields.Many2one(
        "loyalty.program",
        string="Store credit program",
        domain="[('program_type', '=', 'ewallet'), ('company_id', 'in', [id, False])]",
    )
    int_store_credit_product_id = fields.Many2one(
        "product.product",
        string="Store credit top-up product",
        help="Invoiced when a cancellation is refunded as store credit. Have accounting review this before production.",
    )
    int_cancel_notify_user_ids = fields.Many2many(
        "res.users",
        "int_company_cancel_notify_user_rel",
        "company_id",
        "user_id",
        string="Cancel request recipients",
        domain="[('share', '=', False)]",
        help="Told when a dealer asks to cancel an order. The salesperson is always included.",
    )
