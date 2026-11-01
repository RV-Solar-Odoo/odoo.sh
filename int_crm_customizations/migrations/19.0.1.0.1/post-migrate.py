"""Replace the redundant Studio Type of Business alias with the real field."""

from odoo import SUPERUSER_ID, api


FIELD_NAME = "x_studio_type_of_business"
ALIAS_NAME = "x_studio_type_of_business_1"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    alias = env["ir.model.fields"].search([
        ("model", "=", "crm.lead"),
        ("name", "=", ALIAS_NAME),
        ("related", "=", FIELD_NAME),
    ], limit=1)
    if not alias:
        return

    views = env["ir.ui.view"].with_context(active_test=False).search([
        ("model", "=", "crm.lead"),
        ("arch_db", "ilike", ALIAS_NAME),
    ])
    for view in views:
        view.arch_db = str(view.arch_db).replace(ALIAS_NAME, FIELD_NAME)

    alias.unlink()
