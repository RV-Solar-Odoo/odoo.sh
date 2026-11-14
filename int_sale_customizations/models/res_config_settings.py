from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    int_max_pinned = fields.Integer(related="company_id.int_max_pinned", readonly=False)
    int_store_credit_program_id = fields.Many2one(related="company_id.int_store_credit_program_id", readonly=False)
    int_store_credit_product_id = fields.Many2one(related="company_id.int_store_credit_product_id", readonly=False)
    int_cancel_notify_user_ids = fields.Many2many(related="company_id.int_cancel_notify_user_ids", readonly=False)
