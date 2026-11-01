{
    "name": "Hide Odoo Branding",
    "version": "19.0.1.2.0",
    "category": "Website/Website",
    "summary": "Remove Powered by Odoo from pages and emails, and add the company signature to wrapped emails",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["web", "portal", "mail", "auth_signup"],
    "application": False,
    "data": [
        "views/templates.xml",
        "views/email_signature.xml",
        "views/mail_template_views.xml",
    ],
    "post_init_hook": "post_init_hook",
}
