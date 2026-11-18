{
    "name": "CRM Customizations",
    "version": "19.0.1.5.0",
    "category": "Sales/CRM",
    "summary": "Dealer application documents and tax exemption claims, reviewed on the lead and applied to the customer",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["crm", "account", "website_crm", "int_contacts_customizations"],
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "security/lead_document_rules.xml",
        "data/lead_document_labels.xml",
        "data/website_form_fields.xml",
        "views/dealer_invite_views.xml",
        "views/crm_lead_views.xml",
        "views/res_partner_views.xml",
        "views/lead_document_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "int_crm_customizations/static/src/interactions/tax_exemption_upload.js",
        ],
        "web.assets_backend": [
            "int_crm_customizations/static/src/lead_documents/lead_document_dialog.js",
            "int_crm_customizations/static/src/lead_documents/lead_documents_field.js",
            "int_crm_customizations/static/src/lead_documents/lead_documents_field.xml",
            "int_crm_customizations/static/src/lead_documents/lead_documents_field.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
}
