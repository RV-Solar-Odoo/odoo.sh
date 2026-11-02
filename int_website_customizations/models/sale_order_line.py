from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_pricelist_price(self):
        """Website carts charge MAP unless a dealer pricelist is on the order."""
        price = super()._get_pricelist_price()
        order = self.order_id
        if not order.website_id or getattr(self, "is_delivery", False):
            return price
        template = self.product_id.product_tmpl_id
        selling, _msrp, _map_price, _dealer = template._int_website_selling_price(
            price, order.pricelist_id, order.website_id
        )
        return selling
