{
    "name": "Contacts Customizations",
    "version": "19.0.1.0.0",
    "category": "Sales/CRM",
    "summary": "Email a dealer a link to create a password, or recognize an account they already made",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["contacts", "portal", "auth_signup", "sales_team"],
    "application": False,
    "data": [
        "data/mail_template.xml",
        "views/res_partner_views.xml",
    ],
}
