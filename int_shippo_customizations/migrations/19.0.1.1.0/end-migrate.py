from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.int_shippo_customizations.hooks import ensure_package_types
    ensure_package_types(env)
