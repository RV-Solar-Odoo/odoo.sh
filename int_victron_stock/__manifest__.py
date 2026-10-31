{
    "name": "Victron Stock",
    "version": "19.0.1.1.0",
    "category": "Inventory/Inventory",
    "summary": "Show warehouse and Victron availability on the shop, and draft a purchase order for the shortfall",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["stock", "website_sale", "website_sale_stock", "purchase_stock"],
    "application": False,
    "data": [
        "data/victron_cron.xml",
        "views/product_template_views.xml",
        "views/res_config_settings_views.xml",
        "views/website_sale_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_victron_stock/static/src/js/availability.js",
        ],
    },
}
