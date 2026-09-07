{
    "name": "Website Customizations",
    "version": "19.0.1.2.0",
    "category": "Website/Website",
    "summary": "Checkout delivery rules; free UPS Ground on orders of $250 or more",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["website_sale"],
    "application": False,
    "data": [
        "data/delivery_carrier_data.xml",
        "data/delivery_carrier_publish.xml",
        "views/delivery_carrier_views.xml",
    ],
    "post_init_hook": "post_init_hook",
}
