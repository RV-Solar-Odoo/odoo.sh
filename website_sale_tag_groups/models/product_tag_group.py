from odoo import fields, models


class ProductTagGroup(models.Model):
    _name = 'product.tag.group'
    _description = 'Product Tag Group'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    display = fields.Selection(
        selection=[
            ('checkbox', 'Checkboxes'),
            ('select', 'Dropdown'),
        ],
        default='checkbox',
        required=True,
        help="How this group's tags are rendered in the shop filter sidebar.",
    )
    collapsed = fields.Boolean(
        string="Collapsed by default",
        help="Start this section closed on the shop page (it opens automatically "
             "when one of its tags is selected).",
    )
    tag_ids = fields.One2many('product.tag', 'group_id', string="Tags")
    tag_count = fields.Integer(compute='_compute_tag_count')

    _name_uniq = models.Constraint('unique (name)', 'Tag group name already exists!')

    def _compute_tag_count(self):
        for group in self:
            group.tag_count = len(group.tag_ids)
