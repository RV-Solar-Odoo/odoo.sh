from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    int_nexus_alert_user_id = fields.Many2one(
        "res.users",
        string="Sales tax threshold email",
        domain="[('share', '=', False)]",
        config_parameter="int_account.nexus_alert_user_id",
        help="Receives one email on the 1st of the month when a state has crossed "
             "its dollar amount or its transaction count.",
    )
