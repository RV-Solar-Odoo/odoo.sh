from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.config_parameter"].sudo().search([
        ("key", "in", ["int_victron.username", "int_victron.password"]),
    ]).unlink()
