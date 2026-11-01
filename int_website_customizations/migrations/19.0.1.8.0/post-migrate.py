from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    icp = env["ir.config_parameter"].sudo()
    key = "int_website.google_places_api_key"
    if not icp.search([("key", "=", key)], limit=1):
        icp.set_param(key, "")
