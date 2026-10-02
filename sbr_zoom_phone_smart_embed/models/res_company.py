# -*- coding: utf-8 -*-
from odoo import fields, models


DEFAULT_ZOOM_PHONE_EMBED_URL = (
    'https://applications.zoom.us/integration/phone/embeddablephone/home'
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    zoom_phone_enabled = fields.Boolean(
        string='Enable Zoom Phone',
        help='Show Zoom Phone only while this company is active.',
    )
    zoom_phone_embed_url = fields.Char(
        string='Zoom Phone Embed URL',
        default=DEFAULT_ZOOM_PHONE_EMBED_URL,
        help='The Zoom-provided Smart Embed URL. This is not a credential.',
    )
    zoom_smart_embed_auto_dial = fields.Boolean(string='Enable Auto Dial')
    zoom_phone_call_notify = fields.Boolean(string='Enable Call Notifications')
