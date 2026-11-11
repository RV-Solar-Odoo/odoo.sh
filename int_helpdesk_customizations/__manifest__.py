{
    "name": "Helpdesk Customizations",
    "version": "19.0.1.13.0",
    "category": "Services/Helpdesk",
    "summary": "Keep ticket email replies on the ticket, and the dealer Help & Feedback hub",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["helpdesk", "portal", "website", "sale", "int_contacts_customizations"],
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/help_feedback_data.xml",
        "data/help_feedback_setup.xml",
        "views/alert_list_views.xml",
        "views/res_config_settings_views.xml",
        "views/portal_templates.xml",
        "views/website_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_helpdesk_customizations/static/src/scss/help_feedback.scss",
            "int_helpdesk_customizations/static/src/js/help_feedback.js",
        ],
    },
    "post_init_hook": "post_init_hook",
}
