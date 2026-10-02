# -*- coding: utf-8 -*-
{
    'name': 'Zoom Phone Embed',
    'version': '19.0.2.0.0',
    'category': 'Productivity/VOIP',
    'summary': 'Integrates Zoom Phone Smart Embed directly into your Odoo interface '
               'allowing users directly to make calls using zoom',
    'description': """
        Zoom Phone Smart Embed for Odoo
        ================================
    
        This module integrates Zoom Phone Smart Embed directly into Odoo,
        allowing users to initiate and manage calls without leaving the system.
    
        Key Features:
        -------------
        - Embedded Zoom Phone Smart Panel inside Odoo
        - Floating and draggable call bubble
        - Click-to-dial from phone fields (Contacts, Leads, etc.)
        - Optional auto-dial configuration
        - Call event handling for inbound and outbound calls
        - Improved workflow efficiency for Sales and Support teams
    
        This module enhances communication productivity by centralizing
        telephony operations within the Odoo environment.
    """,
    "author": "Softberry Tech",
    "license": "OPL-1",
    "price": 99,
    "currency": "USD",
    'depends': [
        'web',
        'mail',
        'sms',
    ],
    'data': [
        'views/res_config_setting.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sbr_zoom_phone_smart_embed/static/src/css/zoom_phone.css',
            'sbr_zoom_phone_smart_embed/static/src/components/**/*',
            'sbr_zoom_phone_smart_embed/static/src/js/phone_field.js',
            'sbr_zoom_phone_smart_embed/static/src/js/sms_button.js',
            'sbr_zoom_phone_smart_embed/static/src/xml/phone_field_patch.xml',
        ],
    },
    "images": ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}