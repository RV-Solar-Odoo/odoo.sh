from odoo.fields import Domain
from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleShopSearch(WebsiteSale):

    def _int_child_category_entries(self, parent):
        entries = parent.child_id.filtered(lambda c: c.can_access_from_current_website())
        if not request.env.user._is_internal():
            entries = entries.filtered("has_published_products")
        return entries

    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, tags='', **post):
        """A search narrows the products, not the categories. Stock hides any category
        with no match, so put back the same lists the shop shows without a search."""
        response = super().shop(
            page=page, category=category, search=search,
            min_price=min_price, max_price=max_price, tags=tags, **post
        )
        qcontext = getattr(response, "qcontext", None)
        if not qcontext or not qcontext.get("search"):
            return response

        Category = request.env["product.public.category"]
        website_domain = request.website.website_domain()
        root_categories = Category.search(Domain("parent_id", "=", False) & website_domain)
        current = qcontext.get("category")
        qcontext["categories"] = root_categories
        qcontext["search_categories_ids"] = Category.search(website_domain).ids
        qcontext["category_entries"] = current and (
            self._int_child_category_entries(current)
            or self._int_child_category_entries(current.parent_id)
        ) or root_categories
        return response
