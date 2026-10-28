from urllib.parse import urlencode

from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleTagGroups(WebsiteSale):

    def _tag_groups_used_tag_ids(self, search, category):
        """Ids of tags carried by published products in the current category / search.

        Selected tags, attributes and price are deliberately *not* applied so
        sibling tags stay visible once one is picked.
        """
        domain = self._get_shop_domain(search, category, {})
        products = request.env['product.template'].search(domain)
        used = set(products.product_tag_ids.ids)
        used |= set(products.product_variant_ids.additional_product_tag_ids.ids)
        return used

    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, tags='', **post):
        """Two additions on top of stock Odoo:

        1. Auto-clear stale tags. When the shopper moves to a category (or search)
           where a selected tag is not used by any product, that tag is dropped
           from the URL and the page redirects. This stops the "no products,
           filters gone, only Clear Filters left" dead end.
        2. Scope the sidebar tag list to the current category / search so empty
           groups disappear automatically (stock Odoo lists every tag site-wide).
        """
        if tags and isinstance(tags, str):
            resolved_category = self._validate_and_get_category(category)
            used_tag_ids = self._tag_groups_used_tag_ids(search, resolved_category)
            requested = [t for t in tags.split(',') if t]
            kept = [
                t for t in requested
                if request.env['ir.http']._unslug(t)[1] in used_tag_ids
            ]
            if len(kept) != len(requested):
                args = request.httprequest.args.copy()
                if kept:
                    args['tags'] = ','.join(kept)
                else:
                    args.pop('tags', None)
                query = urlencode(list(args.items(multi=True)))
                url = request.httprequest.path + (f'?{query}' if query else '')
                return request.redirect(url)

        response = super().shop(
            page=page, category=category, search=search,
            min_price=min_price, max_price=max_price, tags=tags, **post
        )
        qcontext = getattr(response, 'qcontext', None)
        if not qcontext or not qcontext.get('all_tags'):
            return response

        used_tag_ids = self._tag_groups_used_tag_ids(
            qcontext.get('search'), qcontext.get('category')
        )
        qcontext['all_tags'] = qcontext['all_tags'].filtered(lambda t: t.id in used_tag_ids)
        return response
