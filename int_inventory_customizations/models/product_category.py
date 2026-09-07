from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    ground_shipping_only = fields.Boolean(
        string="Ground shipping only",
        help="Checkout only offers Ground when the cart contains a product in this category.",
    )
    shipping_upcharge = fields.Float(
        string="Shipping upcharge",
        help="Added once to the checkout shipping price when the cart contains a product in this category.",
    )
