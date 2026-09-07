{
    "name": "Website Customizations",
    "version": "19.0.1.3.0",
    "category": "Website/Website",
    "summary": "Checkout delivery rules, free UPS Ground over $250, and shop availability badges",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["website_sale", "website_sale_stock", "int_inventory_customizations"],
    "application": False,
    "data": [
        "data/delivery_carrier_data.xml",
        "data/delivery_carrier_publish.xml",
        "views/delivery_carrier_views.xml",
        "views/website_sale_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
}
