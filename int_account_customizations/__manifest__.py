{
    "name": "Accounting Customizations",
    "summary": "Sales tax threshold emails, and the credit card on My Portal",
    "version": "19.0.1.1.0",
    "category": "Accounting/Accounting",
    "author": "Internal",
    "license": "LGPL-3",
    "application": False,
    "depends": ["account", "sale", "mail", "portal", "int_contacts_customizations"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/nexus_threshold_views.xml",
        "views/nexus_sale_views.xml",
        "views/res_config_settings_views.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_account_customizations/static/src/scss/portal_credit.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
}
