{
    "name": "Sales Customizations",
    "version": "19.0.1.0.1",
    "category": "Sales/Sales",
    "summary": "Carrier tracking links on My Orders and the order page",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["sale_stock", "stock_delivery"],
    "application": False,
    "data": [
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_sale_customizations/static/src/scss/portal_tracking.scss",
        ],
    },
}
