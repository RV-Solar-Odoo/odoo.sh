from urllib.parse import urlencode

from odoo.fields import Domain
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
        return self._tag_groups_carried_tag_ids(products)

    def _tag_groups_carried_tag_ids(self, products):
        used = set(products.product_tag_ids.ids)
        used |= set(products.product_variant_ids.additional_product_tag_ids.ids)
        return used

    def _shop_lookup_products(self, options, post, search, website):
        result = super()._shop_lookup_products(options, post, search, website)
        # shop() needs these to work out which options still lead somewhere.
        request.tag_groups_lookup = (options, post, search, website, result[2])
        return result

    def _tag_groups_hide_dead_ends(self, all_tags, selected_ids):
        """Drop tags that would lead to no products, given the other active filters.

        A group is checked without its own selections, because options within a
        group widen the results. Selected tags always stay so they can be unticked.
        When the filters match nothing there is nothing to narrow by, so everything stays.
        """
        options, post, search, website, products = request.tag_groups_lookup
        if not products:
            return all_tags
        carried = self._tag_groups_carried_tag_ids(products)
        selected = request.env['product.tag'].browse(selected_ids).exists()
        carried_by_group = {}
        for group_id in {tag.group_id.id for tag in selected}:
            others = selected.filtered(lambda t: t.group_id.id != group_id)
            group_options = dict(options, tags=others.ids)
            __, __, group_products = super()._shop_lookup_products(group_options, post, search, website)
            carried_by_group[group_id] = self._tag_groups_carried_tag_ids(group_products)
        return all_tags.filtered(
            lambda t: t.id in selected_ids or t.id in carried_by_group.get(t.group_id.id, carried)
        )

    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, tags='', **post):
        """Two additions on top of stock Odoo:

        1. Auto-clear stale tags. When the shopper moves to a category (or search)
           where a selected tag is not used by any product, that tag is dropped
           from the URL and the page redirects. This stops the "no products,
           filters gone, only Clear Filters left" dead end.
        2. Scope the sidebar tag list to the current category / search so empty
           groups disappear automatically (stock Odoo lists every tag site-wide).
        3. Keep that list when the selected filters match nothing. Stock Odoo builds
           no tags then, which would leave no way to untick the last choice.
        4. Hide options that would lead to no products, given the other filters.
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
        if not qcontext or 'all_tags' not in qcontext:
            return response

        used_tag_ids = self._tag_groups_used_tag_ids(
            qcontext.get('search'), qcontext.get('category')
        )
        if qcontext['all_tags']:
            qcontext['all_tags'] = qcontext['all_tags'].filtered(lambda t: t.id in used_tag_ids)
        else:
            qcontext['all_tags'] = request.env['product.tag'].search(Domain.AND([
                Domain('id', 'in', list(used_tag_ids)),
                Domain('visible_to_customers', '=', True),
                request.website.website_domain(),
            ]))
        qcontext['all_tags'] = self._tag_groups_hide_dead_ends(qcontext['all_tags'], set(qcontext.get('tags') or ()))
        return response
