from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.int_website_customizations.hooks import disable_customer_invoice_email
    disable_customer_invoice_email(env)
