import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Move existing application files onto the new Documents tab.

    - Certificates in x_tax_exemption_document become Tax Exemption Certificate
      documents, reviewed where the exemption was already approved.
    - Files the website form posted as "Attached files:" become Other Attachments.
      Odoo did not record which upload field they came from.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Label = env["int.lead.document.label"]
    Document = env["int.lead.document"].with_context(int_document_no_log=True)
    certificate_label = Label._int_by_code("tax_certificate")
    other_label = Label._int_by_code("other")

    cr.execute("""
        SELECT DISTINCT res_id FROM ir_attachment
         WHERE res_model = 'crm.lead' AND res_field = 'x_tax_exemption_document' AND res_id IS NOT NULL
    """)
    leads = env["crm.lead"].with_context(active_test=False).browse([row[0] for row in cr.fetchall()]).exists()
    leads._int_certificate_to_document()
    approved = Document.search([
        ("lead_id", "in", leads.filtered("x_tax_exemption_approved").ids),
        ("label_id", "=", certificate_label.id),
    ])
    approved.write({"reviewed": True})
    _logger.info("Lead documents: %s certificates moved, %s marked reviewed.", len(leads), len(approved))

    messages = env["mail.message"].search([
        ("model", "=", "crm.lead"),
        ("body", "ilike", "Attached files"),
        ("attachment_ids", "!=", False),
    ])
    taken = Document.search([]).attachment_id
    created = 0
    for message in messages:
        for attachment in message.attachment_ids - taken:
            if attachment.res_model != "crm.lead" or attachment.res_id != message.res_id:
                continue
            Document.create({
                "lead_id": message.res_id,
                "label_id": other_label.id,
                "attachment_id": attachment.id,
            })
            created += 1
    _logger.info("Lead documents: %s website form files filed under Other Attachments.", created)
