from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    int_shippo_api_token = fields.Char(
        string="Shippo API Token",
        config_parameter="int_shippo.api_token",
        help="Paste the test token (shippo_test_…) or live token (shippo_live_…) from Shippo.",
    )
    int_shippo_test_mode = fields.Boolean(
        string="Shippo Test Mode",
        config_parameter="int_shippo.test_mode",
        default=True,
        help="Reminder only. Shippo uses the token itself for test vs live. Keep a test token here until you are ready.",
    )
