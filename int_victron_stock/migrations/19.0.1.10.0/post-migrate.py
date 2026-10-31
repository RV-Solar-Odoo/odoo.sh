from odoo import api, fields, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    icp = env["ir.config_parameter"].sudo()
    endpoint = (icp.get_param("int_victron.endpoint") or "").strip().strip("/")
    if endpoint in ("", "products", "products-extended"):
        icp.set_param("int_victron.endpoint", "/products-stock/")
    cron = env.ref("int_victron_stock.ir_cron_sync_victron_stock", raise_if_not_found=False)
    if cron:
        cron.write({
            "interval_number": 15,
            "interval_type": "minutes",
            "nextcall": fields.Datetime.now(),
        })
