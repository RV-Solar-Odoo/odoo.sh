"""Add the company signature layout to every layoutless email template."""

from odoo import SUPERUSER_ID, api


SIGNATURE_LAYOUT = "int_hide_odoo_branding.mail_notification_signature_only"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["mail.template"].with_context(active_test=False).search([
        ("email_layout_xmlid", "=", False),
    ]).write({
        "email_layout_xmlid": SIGNATURE_LAYOUT,
    })
