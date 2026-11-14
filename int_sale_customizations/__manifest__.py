{
    "name": "Sales Customizations",
    "version": "19.0.1.1.0",
    "category": "Sales/Sales",
    "summary": "Dealer orders: search, backorders, pins, export, PO upload, and cancellation",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": [
        "sale_stock",
        "stock_delivery",
        "website_sale",
        "account",
        "payment",
        "loyalty",
        "int_contacts_customizations",
        "int_account_customizations",
    ],
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "views/portal_templates.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_sale_customizations/static/src/scss/portal_tracking.scss",
        ],
    },
}
