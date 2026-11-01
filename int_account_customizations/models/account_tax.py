from odoo import fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    int_nexus_treatment = fields.Selection(
        [
            ("normal", "Normal sales tax"),
            ("resale", "Resale exemption"),
            ("not_collecting", "Not collecting this state yet"),
        ],
        string="Nexus treatment",
        default="normal",
        required=True,
        help="Resale exemption marks the line as wholesale. "
             "Not collecting means the destination tax is not being charged yet; "
             "the product still counts as a normal sale.",
    )
