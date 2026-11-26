from urllib.parse import quote as url_quote

from odoo import _
from odoo.exceptions import AccessError, UserError
from odoo.http import request, route
from odoo.tools.misc import formatLang

from odoo.addons.sale.controllers.portal import CustomerPortal

# Keep this in step with CUSTOMER_PRICE_KEYS. Wholesale is not in the list.
PUBLIC_PRODUCT_KEYS = ("id", "name", "sku", "price", "map_missing")


def _int_redirect(path, error=None):
    if error:
        path = "%s?int_error=%s" % (path, url_quote(str(error)))
    return request.redirect(path)


class IntCustomerQuotePortal(CustomerPortal):
    """Quotes a dealer writes for their own customer. /my/quotes stays RV Solar's."""

    def _int_quote_company(self):
        return request.website.company_id or request.env.company

    def _int_quote_user(self):
        user = request.env.user
        if not user or user._is_public() or not user.int_portal_can("create_quotes"):
            return None
        return user

    def _int_quote_owner(self):
        """Portal owners set the company default. Staff use the contact form."""
        user = self._int_quote_user()
        if not user or not user.share or not user.int_portal_can("manage_users"):
            return None
        return user

    @route("/my/customer-quotes", type="http", auth="user", website=True, methods=["GET", "POST"], sitemap=False)
    def int_customer_quotes(self, **post):
        user = self._int_quote_user()
        if not user:
            return request.redirect("/my")
        company = self._int_quote_company()
        Quote = request.env["int.dealer.quote"]
        if request.httprequest.method == "POST":
            try:
                quote = Quote._int_create(
                    user, company, post.get("customer_name"),
                    email=post.get("customer_email"), phone=post.get("customer_phone"),
                )
            except (UserError, AccessError) as exc:
                return _int_redirect("/my/customer-quotes", exc.args[0])
            return request.redirect("/my/customer-quotes/%s" % quote.id)
        commercial = user.partner_id.commercial_partner_id
        basis = commercial.int_quote_price_basis if commercial.int_quote_price_basis in ("map", "msrp") else "map"
        return request.render("int_sale_customizations.portal_customer_quotes", {
            "page_name": "int_customer_quotes",
            "quotes": Quote._int_for_user(user, company),
            "int_basis": "MSRP" if basis == "msrp" else "MAP",
            "int_can_set_basis": bool(self._int_quote_owner()),
            "int_error": post.get("int_error") or "",
        })

    @route("/my/customer-quotes/settings", type="http", auth="user", website=True, methods=["GET", "POST"], sitemap=False)
    def int_customer_quote_settings(self, **post):
        user = self._int_quote_owner()
        if not user:
            return _int_redirect("/my/customer-quotes", _("Only the account owner can change customer quote prices."))
        if request.httprequest.method == "POST":
            try:
                request.env["res.partner"]._int_set_quote_basis(user, post.get("price_basis"))
            except (UserError, AccessError) as exc:
                return _int_redirect("/my/customer-quotes/settings", exc.args[0])
            return request.redirect("/my/customer-quotes/settings")
        commercial = user.partner_id.commercial_partner_id
        basis = commercial.int_quote_price_basis if commercial.int_quote_price_basis in ("map", "msrp") else "map"
        return request.render("int_sale_customizations.portal_customer_quote_settings", {
            "page_name": "int_quote_prices",
            "commercial": commercial,
            "int_basis": basis,
            "int_error": post.get("int_error") or "",
        })

    @route("/my/customer-quotes/products", type="http", auth="user", website=True, methods=["GET"], sitemap=False)
    def int_customer_quote_products(self, q="", quote_id=None, **kwargs):
        """Customer price only. The payload is PUBLIC_PRODUCT_KEYS plus a label and image."""
        user = self._int_quote_user()
        if not user or not quote_id:
            return request.make_json_response({"products": []}, status=403 if not user else 200)
        company = self._int_quote_company()
        quote = request.env["int.dealer.quote"]._int_for_user(user, company, quote_id)
        if len(quote) != 1:
            return request.make_json_response({"products": []})
        currency = quote.currency_id or company.currency_id
        products = []
        for product in quote._int_find_products(company, q, request.website):
            choice = quote._int_product_choice(product)
            payload = {key: choice[key] for key in PUBLIC_PRODUCT_KEYS}
            payload["price_label"] = formatLang(request.env, choice["price"], currency_obj=currency)
            payload["image"] = "/web/image/product.product/%s/image_128" % product.id
            products.append(payload)
        return request.make_json_response({"products": products})

    @route(
        "/my/customer-quotes/<int:quote_id>",
        type="http", auth="user", website=True, methods=["GET", "POST"], sitemap=False,
    )
    def int_customer_quote(self, quote_id, **post):
        user = self._int_quote_user()
        if not user:
            return request.redirect("/my")
        company = self._int_quote_company()
        Quote = request.env["int.dealer.quote"]
        quote = Quote._int_for_user(user, company, quote_id)
        if not quote:
            return request.redirect("/my/customer-quotes")
        if request.httprequest.method == "POST":
            try:
                quote._int_apply(user, post, website=request.website)
            except (UserError, AccessError) as exc:
                return _int_redirect("/my/customer-quotes/%s" % quote.id, exc.args[0])
            return request.redirect("/my/customer-quotes/%s" % quote.id)
        return request.render("int_sale_customizations.portal_customer_quote", {
            "page_name": "int_customer_quote",
            "quote": quote,
            "addresses": Quote._int_customer_addresses(quote.partner_id),
            "int_error": post.get("int_error") or "",
        })
