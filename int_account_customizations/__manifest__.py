{
    "name": "Accounting Customizations",
    "summary": "Emails when a state's sales tax threshold is crossed",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Internal",
    "license": "LGPL-3",
    "application": False,
    "depends": ["account", "sale", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/nexus_threshold_views.xml",
        "views/nexus_sale_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "post_init_hook": "post_init_hook",
}
