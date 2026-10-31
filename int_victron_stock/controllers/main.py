from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale


class IntVictronWebsiteSale(WebsiteSale):

    @route("/shop/victron_ship_when", type="http", auth="public", website=True, methods=["POST"])
    def shop_victron_ship_when(self, policy=None, **kwargs):
        order = request.cart
        if order and policy in ("direct", "one") and order._int_victron_needs_ship_choice():
            order.int_ship_policy_chosen = True
            order.picking_policy = policy
        return request.redirect("/shop/checkout")
