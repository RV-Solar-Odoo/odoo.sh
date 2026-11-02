from odoo import models
from odoo.http import request


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _to_markup_data(self, website):
        """Tell search engines the price a visitor actually pays."""
        data = super()._to_markup_data(website)
        template = self.product_tmpl_id
        if not template._int_map_amount() and not template._int_is_dealer_pricelist(
            request.pricelist, website
        ):
            return data
        pricelist_price = request.pricelist._get_product_price(
            self, quantity=1, currency=website.currency_id
        )
        selling, _msrp, _map_price, _dealer = template._int_website_selling_price(
            pricelist_price, request.pricelist, website
        )
        data["offers"]["price"] = template._int_taxed_website_price(selling, website, self)
        return data
