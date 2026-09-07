from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    int_victron_username = fields.Char(
        string="Victron E-Order Username",
        config_parameter="int_victron.username",
    )
    int_victron_password = fields.Char(
        string="Victron E-Order Password",
        config_parameter="int_victron.password",
    )
    int_victron_endpoint = fields.Char(
        string="Victron Stock Endpoint",
        config_parameter="int_victron.endpoint",
        default="/products-extended/",
        help="Path appended to https://eorder.victronenergy.com/api/v1. Keep the trailing slash.",
    )
    int_victron_sku_field = fields.Char(
        string="Victron SKU Field",
        config_parameter="int_victron.sku_field",
        default="sku",
        help="Name of the article-code key in the E-Order response.",
    )
    int_victron_qty_field = fields.Char(
        string="Victron Quantity Field",
        config_parameter="int_victron.qty_field",
        default="stock",
        help="Name of the stock-quantity key in the E-Order response.",
    )
    int_victron_lead_time_label = fields.Char(
        string="Victron Lead Time Label",
        config_parameter="int_victron.lead_time_label",
        default="Ships in about 2 weeks",
        help="Shown on the webshop when only Victron has stock.",
    )
