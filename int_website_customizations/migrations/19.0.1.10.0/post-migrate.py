"""Refresh stored pickup names after the display label change."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    partners = env["res.partner"].with_context(active_test=False).search([
        ("is_pickup_location", "=", True),
    ])
    if not partners:
        return
    partners.modified(["name"])
    partners.flush_recordset(["complete_name"])
