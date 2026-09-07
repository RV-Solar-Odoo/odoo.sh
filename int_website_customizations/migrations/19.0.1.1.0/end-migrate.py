from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.int_website_customizations.hooks import unpublish_standard_delivery
    unpublish_standard_delivery(env)
