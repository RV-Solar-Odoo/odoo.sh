from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _int_availability_lines(self):
        self.ensure_one()
        return self.product_tmpl_id._int_availability_lines(self)

    def _get_max_quantity(self, website, sale_order, **kwargs):
        """Don't tell the browser a max when Victron can cover more than we have on hand.

        The cart still refuses an order larger than our stock plus Victron's, without
        sending Victron's quantity to the page.
        """
        self.ensure_one()
        if self.is_storable and self.product_tmpl_id._int_victron_feed_qty() > 0:
            return None
        return super()._get_max_quantity(website, sale_order, **kwargs)
