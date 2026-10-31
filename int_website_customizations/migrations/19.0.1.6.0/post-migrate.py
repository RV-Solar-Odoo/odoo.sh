from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.int_website_customizations.hooks import show_payment_brand_on_receipt
    show_payment_brand_on_receipt(env)
