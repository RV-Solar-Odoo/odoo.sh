from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    def set_values(self):
        super().set_values()
        if self.int_victron_vendor_id and self.int_victron_buyer_id:
            self.int_victron_vendor_id.buyer_id = self.int_victron_buyer_id

    int_victron_token = fields.Char(
        string="Victron API Token",
        config_parameter="int_victron.token",
        help="E-Order API key. Sent as the password, with the username token.",
    )
    int_victron_endpoint = fields.Char(
        string="Victron Stock Endpoint",
        config_parameter="int_victron.endpoint",
        default="/products-stock/",
        help="Base path on https://eorder.victronenergy.com/api/v1. Each of our SKUs is requested under it, for example /products-stock/PMP242305102/.",
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
        default="stock_quantity",
        help="Name of the stock-quantity key in the E-Order response. The feed calls this stock_quantity.",
    )
    int_victron_lead_time_label = fields.Char(
        string="Victron Lead Time",
        config_parameter="int_victron.lead_time_label",
        default="within 7–10 days",
        help="Shown after the supplier quantity, for example \"20+ available — ships within 7–10 days\".",
    )
    int_victron_vendor_id = fields.Many2one(
        "res.partner",
        string="Victron Vendor",
        config_parameter="int_victron.vendor_partner_id",
        help="Contact that receives the draft purchase order when the warehouse cannot fill an order.",
    )
    int_victron_buyer_id = fields.Many2one(
        "res.users",
        string="Victron Buyer",
        config_parameter="int_victron.buyer_user_id",
        domain="[('share', '=', False)]",
        help="Assigned to those draft purchase orders, with a to-do to finish and send them. "
             "Leave empty to use the user named Casey Shirts.",
    )
