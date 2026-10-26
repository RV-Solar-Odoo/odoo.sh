from odoo import fields, models


class ProductTag(models.Model):
    _inherit = 'product.tag'

    group_id = fields.Many2one(
        'product.tag.group',
        string="Filter Group",
        ondelete='set null',
        index=True,
        help="Shop sidebar section this tag is shown under. "
             "Tags without a group are listed under a generic 'Tags' section.",
    )
