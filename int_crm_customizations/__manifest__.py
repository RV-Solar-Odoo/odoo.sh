{
    "name": "CRM Customizations",
    "version": "19.0.1.0.1",
    "category": "Sales/CRM",
    "summary": "Review dealer tax exemption claims on the lead and apply approved ones to the customer",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["crm", "account", "website_crm"],
    "application": False,
    "data": [
        "data/website_form_fields.xml",
        "views/crm_lead_views.xml",
        "views/res_partner_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_crm_customizations/static/src/interactions/tax_exemption_upload.js",
        ],
    },
    "post_init_hook": "post_init_hook",
}
