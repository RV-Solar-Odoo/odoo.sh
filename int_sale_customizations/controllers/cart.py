from urllib.parse import quote

from odoo import _
from odoo.http import request, route
from odoo.tools.translate import _lt

from odoo.addons.payment.controllers.portal import PaymentPortal
from odoo.addons.website_sale.controllers.cart import Cart
from odoo.addons.website_sale.controllers.main import WebsiteSale


class Cart(Cart):

    def _int_order_blocked(self):
        return request.env.user.int_portal_ordering_blocked()

    @route(route="/shop/cart/add", type="jsonrpc", auth="public", methods=["POST"], website=True, sitemap=False)
    def add_to_cart(self, product_template_id, product_id, quantity=1.0, uom_id=None,
                    product_custom_attribute_values=None, no_variant_attribute_value_ids=None,
                    linked_products=None, **kwargs):
        if self._int_order_blocked():
            return {"error": _("Ask your account owner to order.")}
        return super().add_to_cart(
            product_template_id, product_id, quantity=quantity, uom_id=uom_id,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            linked_products=linked_products, **kwargs,
        )

    @route(route="/shop/cart/update", type="jsonrpc", auth="public", methods=["POST"], website=True, sitemap=False)
    def update_cart(self, line_id, quantity, product_id=None, **kwargs):
        if self._int_order_blocked() and float(quantity or 0) > 0:
            return {"error": _("Ask your account owner to order.")}
        return super().update_cart(line_id, quantity, product_id=product_id, **kwargs)


class PaymentPortal(PaymentPortal):

    @route("/my/payment_method", type="http", methods=["GET"], auth="user", website=True)
    def payment_method(self, **kwargs):
        user = request.env.user
        if user.share and not user.int_portal_can("make_payments"):
            return request.redirect("/my")
        return super().payment_method(**kwargs)


class WebsiteSale(WebsiteSale):

    @route("/shop/checkout", type="http", methods=["GET"], auth="public", website=True, sitemap=False, list_as_website_content=_lt("Shop Checkout"))
    def shop_checkout(self, try_skip_step=None, **query_params):
        if request.env.user.int_portal_ordering_blocked():
            return request.redirect("/shop/cart?int_error=%s" % quote(_("Ask your account owner to order.")))
        return super().shop_checkout(try_skip_step=try_skip_step, **query_params)
