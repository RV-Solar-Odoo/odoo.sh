from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    int_marketplace_collected = fields.Boolean(
        string="Marketplace collected the tax",
        help="Turn this on when a marketplace collected sales tax on the order. "
             "Website, phone, and dealer orders stay off. States that exclude "
             "marketplace sales then leave the order out.",
    )
