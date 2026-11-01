{
    "name": "Hide Odoo Branding",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "summary": "Remove Powered by Odoo from pages, email layouts and saved email templates",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["web", "portal", "mail", "auth_signup"],
    "application": False,
    "data": [
        "views/templates.xml",
    ],
    "post_init_hook": "post_init_hook",
}
