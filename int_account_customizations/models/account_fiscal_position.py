from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _inherit = "account.fiscal.position"

    int_nexus_resale = fields.Boolean(
        string="Wholesale / resale",
        help="Sales on this position are for resale. They count only in states "
             "whose threshold includes wholesale.",
    )
