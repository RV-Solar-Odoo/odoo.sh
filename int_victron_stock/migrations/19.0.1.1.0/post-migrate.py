from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    icp = env["ir.config_parameter"].sudo()
    current = (icp.get_param("int_victron.lead_time_label") or "").strip()
    if current in ("", "Ships in about 2 weeks"):
        icp.set_param("int_victron.lead_time_label", "within 7–10 days")
