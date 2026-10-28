from odoo.http import request, route

from odoo.addons.website_sale.controllers.delivery import Delivery
from odoo.addons.website_sale.controllers.main import WebsiteSale


class IntShippoWebsiteSale(WebsiteSale):

    @route()
    def shop_checkout(self, try_skip_step=None, **query_params):
        if order_sudo := request.cart:
            order_sudo._int_drop_unchosen_pickup()
        return super().shop_checkout(try_skip_step=try_skip_step, **query_params)


class IntShippoDelivery(Delivery):

    @route()
    def shop_set_delivery_method(self, dm_id=None, **kwargs):
        # The checkout page also calls this on load for the method already selected;
        # only a switch to a different method is the customer's own choice.
        order_sudo = request.cart
        switching = bool(order_sudo and dm_id and int(dm_id) != order_sudo.carrier_id.id)
        result = super().shop_set_delivery_method(dm_id=dm_id, **kwargs)
        if switching and order_sudo.carrier_id.id == int(dm_id):
            order_sudo.int_chosen_carrier_id = order_sudo.carrier_id
        return result
