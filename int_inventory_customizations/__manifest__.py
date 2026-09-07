{
    "name": "Inventory Customizations",
    "version": "19.0.2.2.0",
    "category": "Inventory/Inventory",
    "summary": "Adds RVSB product fields, form layout, battery Ground shipping rules, and Victron E-Order stock sync",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["product", "stock", "purchase", "stock_delivery"],
    "application": False,
    "data": [
        "data/product_category_data.xml",
        "data/product_category_shipping.xml",
        "data/victron_cron.xml",
        "views/product_category_views.xml",
        "views/product_template_views.xml",
        "views/res_config_settings_views.xml",
    ],
}
