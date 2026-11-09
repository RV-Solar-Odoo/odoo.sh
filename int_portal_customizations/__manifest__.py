{
    "name": "Portal Customizations",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "summary": "Shipment tracking, the sales rep card, and the credit card on My Portal",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["portal", "sale_stock", "stock_delivery", "account"],
    "application": False,
    "data": [
        "views/portal_templates.xml",
        "views/res_partner_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_portal_customizations/static/src/scss/portal_account.scss",
        ],
    },
}
