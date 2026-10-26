from odoo import api, models
from odoo.fields import Domain


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _search_get_detail(self, website, order, options):
        """Filter AND across tag groups, OR within a group.

        Standard Odoo ORs every selected tag together, so picking "12V" and
        "Marine" returns anything that is 12V *or* marine. With groups, a
        shopper expects 12V *and* marine. Tags with no group keep the
        standard OR behaviour among themselves.
        """
        tags = options.get('tags')
        if not tags:
            return super()._search_get_detail(website, order, options)

        if isinstance(tags, str):
            tags = tags.split(',')
        tag_ids = [int(t) for t in tags if t]
        tag_records = self.env['product.tag'].browse(tag_ids).exists()

        # Let super() build everything else, but without the tag domain.
        options = dict(options, tags=None)
        detail = super()._search_get_detail(website, order, options)

        buckets = {}
        for tag in tag_records:
            buckets.setdefault(tag.group_id.id or 0, []).append(tag.id)
        for ids in buckets.values():
            detail['base_domain'].append(Domain.OR([
                Domain('product_tag_ids', 'in', ids),
                Domain('product_variant_ids.additional_product_tag_ids', 'in', ids),
            ]))
        return detail
