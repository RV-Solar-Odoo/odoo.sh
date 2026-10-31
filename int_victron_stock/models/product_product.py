from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _int_availability_lines(self):
        self.ensure_one()
        return self.product_tmpl_id._int_availability_lines(self)

    def _website_show_quick_add(self):
        self.ensure_one()
        return super()._website_show_quick_add() and self.product_tmpl_id._int_can_order_online(self)

    def _is_add_to_cart_allowed(self):
        self.ensure_one()
        return super()._is_add_to_cart_allowed() and self.product_tmpl_id._int_can_order_online(self)

    def _get_max_quantity(self, website, sale_order, **kwargs):
        """Don't tell the browser a max when Victron can cover more than we have on hand.

        The cart still refuses an order larger than our stock plus Victron's, without
        sending Victron's quantity to the page.
        """
        self.ensure_one()
        template = self.product_tmpl_id
        if self.is_storable and not template._int_can_order_online(self):
            return 0
        if self.is_storable and template._int_victron_feed_qty() > 0:
            return None
        return super()._get_max_quantity(website, sale_order, **kwargs)
