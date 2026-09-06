{
    "name": "Shippo Customizations",
    "version": "19.0.1.5.1",
    "category": "Inventory/Delivery",
    "summary": "Buy Shippo labels from warehouse deliveries and quote UPS, USPS, and FedEx on the website",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["stock_delivery", "website_sale"],
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "data/delivery_carrier_data.xml",
        "data/shippo_box_data.xml",
        "views/shippo_box_views.xml",
        "views/res_config_settings_views.xml",
        "views/delivery_carrier_views.xml",
        "views/stock_picking_views.xml",
        "wizard/shippo_rate_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "int_shippo_customizations/static/src/shippo_rate_list.js",
            "int_shippo_customizations/static/src/shippo_rate_list.css",
        ],
    },
}
