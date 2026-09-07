{
    "name": "Victron Stock",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Read Victron E-Order stock as backup availability and show shipping times on the shop",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["stock", "website_sale", "website_sale_stock"],
    "application": False,
    "data": [
        "data/victron_cron.xml",
        "views/product_template_views.xml",
        "views/res_config_settings_views.xml",
        "views/website_sale_templates.xml",
    ],
}
