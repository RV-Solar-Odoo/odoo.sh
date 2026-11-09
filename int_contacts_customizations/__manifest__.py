{
    "name": "Contacts Customizations",
    "version": "19.0.1.1.0",
    "category": "Sales/CRM",
    "summary": "Dealer account email, portal role, and the sales rep card on My Portal",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["contacts", "portal", "auth_signup", "sales_team"],
    "application": False,
    "data": [
        "data/mail_template.xml",
        "views/res_partner_views.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_contacts_customizations/static/src/scss/portal_sales_rep.scss",
        ],
    },
}
