{
    "name": "Website Customizations",
    "version": "19.0.1.15.6",
    "category": "Website/Website",
    "summary": "Checkout delivery rules, MAP pricing on the shop, and a Google check on public address forms",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["website_sale", "website_sale_collect"],
    "application": False,
    "data": [
        "data/delivery_carrier_data.xml",
        "data/delivery_carrier_publish.xml",
        "views/delivery_carrier_views.xml",
        "views/res_config_settings_views.xml",
        "views/website_sale_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_website_customizations/static/src/scss/address_places.scss",
            "int_website_customizations/static/src/interactions/address_places.js",
            "int_website_customizations/static/src/interactions/shop_search.js",
            "int_website_customizations/static/src/scss/shop_search.scss",
            "int_website_customizations/static/src/interactions/shop_search_bar.js",
            "int_website_customizations/static/src/scss/map_price.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
}
