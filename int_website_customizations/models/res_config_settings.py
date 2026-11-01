from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    int_google_places_api_key = fields.Char(
        string="Google Places API Key",
        config_parameter="int_website.google_places_api_key",
        help="Places API (New) and Address Validation API must both be enabled on this key. "
             "Checkout, the customer account, and website forms that ask for a street use it. "
             "The key stays on the server.",
    )
