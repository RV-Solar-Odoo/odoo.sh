# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    zoom_phone_enabled = fields.Boolean(
        related='company_id.zoom_phone_enabled', readonly=False,
    )
    zoom_phone_embed_url = fields.Char(
        related='company_id.zoom_phone_embed_url', readonly=False,
    )
    zoom_smart_embed_auto_dial = fields.Boolean(
        string='Enable Auto Dial',
        related='company_id.zoom_smart_embed_auto_dial', readonly=False,
    )

    is_call_notification_enabled = fields.Boolean(
        string='Enable Notification',
        related='company_id.zoom_phone_call_notify', readonly=False,
    )
