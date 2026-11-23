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
    int_shippo_freight_over_lb = fields.Float(
        string="Freight Over (lb)",
        config_parameter="int_shippo.freight_over_lb",
        default=500.0,
        help="Website carts heavier than this, counting only what ships now, are offered "
             "freight instead of parcel rates. 0 turns the weight check off. Carts that need "
             "more than 20 boxes, or have an item over 150 lb, are freight whatever this says.",
    )
