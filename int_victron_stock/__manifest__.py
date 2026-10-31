{
    "name": "Victron Stock",
    "version": "19.0.1.7.0",
    "category": "Inventory/Inventory",
    "summary": "Show warehouse and Victron availability on the shop, and draft a purchase order for the shortfall",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["stock", "website_sale", "website_sale_stock", "website_sale_collect", "purchase_stock"],
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "data/victron_cron.xml",
        "views/product_template_views.xml",
        "views/victron_feed_views.xml",
        "views/res_config_settings_views.xml",
        "views/website_sale_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_victron_stock/static/src/scss/shop_availability.scss",
            "int_victron_stock/static/src/js/availability.js",
            "int_victron_stock/static/src/xml/click_and_collect_availability.xml",
        ],
    },
}
