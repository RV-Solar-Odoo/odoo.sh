from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_pricelist_price(self):
        """Website carts charge MAP unless the contact has a dealer pricelist."""
        price = super()._get_pricelist_price()
        order = self.order_id
        if not order.website_id or getattr(self, "is_delivery", False):
            return price
        template = self.product_id.product_tmpl_id
        partner = order.partner_id
        if template._int_is_dealer_contact(partner, order.website_id):
            contact_pl = template._int_contact_pricelist(partner, order.website_id)
            if contact_pl and contact_pl != order.pricelist_id:
                return contact_pl._get_product_price(
                    self.product_id,
                    quantity=self.product_uom_qty or 1.0,
                    uom=self.product_uom_id,
                    currency=order.currency_id,
                )
            return price
        selling, _msrp, _map_price, _dealer = template._int_website_selling_price(
            price, partner, order.website_id
        )
        return selling
