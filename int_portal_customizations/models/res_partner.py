from odoo import fields, models

PORTAL_ROLES = [
    ("owner", "Owner"),
    ("buyer", "Buyer"),
    ("accountant", "Accountant"),
    ("viewer", "Viewer"),
]


class ResPartner(models.Model):
    _inherit = "res.partner"

    int_portal_role = fields.Selection(
        PORTAL_ROLES,
        string="Portal role",
        default="owner",
        groups="base.group_user",
        help="What this contact can see in My Portal. Owner and Accountant can see the credit limit. Buyer and Viewer cannot.",
    )
