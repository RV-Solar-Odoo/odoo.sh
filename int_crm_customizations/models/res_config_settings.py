from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    int_cert_reminder_days = fields.Char(related="company_id.int_cert_reminder_days", readonly=False)
    int_cert_reviewer_id = fields.Many2one(related="company_id.int_cert_reviewer_id", readonly=False)
