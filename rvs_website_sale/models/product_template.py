from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_data_sheet = fields.Binary(
        string="Data Sheet",
        attachment=False,
        help="PDF or document made available for download on the website product page.",
    )
    product_data_sheet_filename = fields.Char(string="Data Sheet Filename")
