# -*- coding: utf-8 -*-
from markupsafe import Markup, escape
from urllib.parse import urlparse

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class ZoomConfigController(http.Controller):
    _zoom_host = 'applications.zoom.us'

    @http.route(
        '/zoom/config',
        type='jsonrpc',
        auth='user',
        methods=['POST'],
    )
    def get_zoom_config(self, company_id):
        """Return the active company's public Smart Embed configuration.

        This endpoint deliberately never returns a Zoom client secret, password,
        token, or any other credential. A user without settings access can safely
        call it because the selected company's public feature configuration is
        read server-side.
        """
        try:
            company = request.env['res.company'].browse(company_id)
            embed_url = company.zoom_phone_embed_url or ''
            parsed_url = urlparse(embed_url)
            if not company.zoom_phone_enabled or (
                parsed_url.scheme != 'https' or parsed_url.netloc != self._zoom_host
            ):
                return {'enabled': False}
            return {
                'enabled': True,
                'company_id': company.id,
                'embed_url': embed_url,
                'zoom_origin': '%s://%s' % (parsed_url.scheme, parsed_url.netloc),
                'auto_dial': company.zoom_smart_embed_auto_dial,
                'call_notification': company.zoom_phone_call_notify,
            }
        except (AttributeError, AccessError):
            # Keep the backend usable during an incomplete upgrade or when a
            # restricted user cannot resolve the company configuration.
            return {'enabled': False}

    @http.route(
        '/add/zoom/call/log',
        type='jsonrpc',
        auth='user',
        methods=['POST'],
    )
    def add_zoom_call_log(self, res_model=None, res_id=None, call=None, **kwargs):
        """Post a safe Zoom summary only where the current user can write."""
        if not isinstance(res_model, str) or type(res_id) is not int or res_id <= 0 or not isinstance(call, dict):
            return False
        try:
            model = request.env[res_model]
        except KeyError:
            return False
        record = model.browse(res_id).exists()
        if not record or not hasattr(record, 'message_post'):
            return False
        try:
            record.check_access('write')
            record.check_access_rule('write')
        except AccessError:
            return False

        caller = call.get('caller') if isinstance(call.get('caller'), dict) else {}
        callee = call.get('callee') if isinstance(call.get('callee'), dict) else {}
        caller_name = caller.get('name') or caller.get('phoneNumber') or 'Unknown'
        callee_name = callee.get('name') or callee.get('phoneNumber') or 'Unknown'
        result = str(call.get('result') or 'Unknown').replace('_', ' ').title()
        date_time = str(call.get('dateTime') or '')
        when = Markup('<br/>%s') % escape(date_time) if date_time else Markup('')
        body = Markup('<p><strong>Zoom Phone: %s</strong><br/>%s called %s%s</p>') % (
            escape(result), escape(str(caller_name)), escape(str(callee_name)), when,
        )
        record.message_post(body=body)
        return True
