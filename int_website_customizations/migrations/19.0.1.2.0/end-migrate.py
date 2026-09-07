from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.int_website_customizations.hooks import configure_checkout_shipping
    configure_checkout_shipping(env)
