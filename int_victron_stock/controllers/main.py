from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale


class IntVictronWebsiteSale(WebsiteSale):

    def _int_selected_ships(self, ships):
        return set((ships or "").split(",")) & {"now", "later"}

    def _get_search_options(self, *args, **post):
        options = super()._get_search_options(*args, **post)
        options["int_ships"] = self._int_selected_ships(post.get("ships"))
        return options

    def _shop_get_query_url_kwargs(self, search, min_price, max_price, **kwargs):
        """Keep the filter on across other filters, categories and sorting."""
        query = super()._shop_get_query_url_kwargs(search, min_price, max_price, **kwargs)
        query["ships"] = kwargs.get("ships")
        return query

    def _get_additional_shop_values(self, values, **kwargs):
        shop_values = super()._get_additional_shop_values(values, **kwargs)
        selected = self._int_selected_ships(kwargs.get("ships"))
        shop_values["int_ship_filters"] = [
            {
                "value": value,
                "label": label,
                "checked": value in selected,
                "href": values["keep"](ships=",".join(sorted(selected ^ {value})) or 0),
            }
            for value, label in (
                ("now", request.env._("Ships immediately")),
                ("later", request.env._("Ships in 7 days")),
            )
        ]
        return shop_values

    @route("/shop/victron_ship_when", type="http", auth="public", website=True, methods=["POST"])
    def shop_victron_ship_when(self, policy=None, **kwargs):
        order = request.cart
        if order and policy in ("direct", "one") and order._int_victron_needs_ship_choice():
            order.int_ship_policy_chosen = True
            order.picking_policy = policy
        return request.redirect("/shop/checkout")
