from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleTagGroups(WebsiteSale):

    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, tags='', **post):
        """Scope the sidebar tag list to the current category / search.

        Stock Odoo lists every published tag site-wide. Here `all_tags` is
        narrowed to tags carried by products that match the current category
        and search term. Selected tags, attributes and price are deliberately
        *not* applied so sibling tags stay visible once one is picked.
        Empty groups therefore disappear automatically.
        """
        response = super().shop(
            page=page, category=category, search=search,
            min_price=min_price, max_price=max_price, tags=tags, **post
        )
        qcontext = getattr(response, 'qcontext', None)
        if not qcontext or not qcontext.get('all_tags'):
            return response

        domain = self._get_shop_domain(qcontext.get('search'), qcontext.get('category'), {})
        scoped_products = request.env['product.template'].search(domain)
        used_tag_ids = set(scoped_products.product_tag_ids.ids)
        used_tag_ids |= set(scoped_products.product_variant_ids.additional_product_tag_ids.ids)

        qcontext['all_tags'] = qcontext['all_tags'].filtered(lambda t: t.id in used_tag_ids)
        return response
