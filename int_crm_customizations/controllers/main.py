import json

from odoo import http
from odoo.http import request
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.website.controllers.form import WebsiteForm

EXEMPT_FIELD = "x_is_tax_exempt"
# The pre-module Studio checkbox. The live form has used it in place of EXEMPT_FIELD.
STUDIO_EXEMPT_FIELD = "x_studio_tax_exempt"
REASON_FIELD = "x_tax_exemption_reason"
DOCUMENT_FIELD = "x_tax_exemption_document"
# Extension -> content types it may be detected as. Older libmagic calls BMP image/x-ms-bmp.
ALLOWED_DOCUMENTS = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".bmp": {"image/bmp", "image/x-ms-bmp"},
}


# Labels the website editor gives the upload when it is added as a custom field
# instead of the lead's Tax Exemption Certificate field. Compared lowercased.
DOCUMENT_LABELS = {"exemption certificate", "tax exemption certificate"}


def _int_base_name(key):
    return key.split("[", 1)[0]


def int_bind_tax_exemption_document(params):
    """Send a custom "Exemption Certificate" upload to the lead's certificate field.

    The live form's upload was built in the editor as a custom field, so it posts
    as "Exemption Certificate[0][0]" and would only be attached to the chatter.
    Renamed, Odoo stores it on x_tax_exemption_document like the bound field.
    """
    for key in list(params):
        if _int_base_name(key).strip().lower() in DOCUMENT_LABELS:
            value = params.pop(key)
            params[DOCUMENT_FIELD + key[len(_int_base_name(key)):]] = value


def int_tax_exemption_error(env, params):
    """Check the claim, and drop what a dealer filled in before unticking the box."""
    int_bind_tax_exemption_document(params)
    # Either checkbox counts, and the lead gets the module's tick so the
    # Tax Exemption tab and Grant Tax Exemption see the claim.
    if params.get(STUDIO_EXEMPT_FIELD) and not params.get(EXEMPT_FIELD):
        params[EXEMPT_FIELD] = params[STUDIO_EXEMPT_FIELD]
    # The website form sends a file under an indexed name, like field[0][0].
    document_keys = [key for key in params if _int_base_name(key) == DOCUMENT_FIELD]
    if not params.get(EXEMPT_FIELD):
        params.pop(REASON_FIELD, None)
        for key in document_keys:
            params.pop(key)
        return None

    reasons = env["crm.lead"]._fields[REASON_FIELD].get_values(env)
    if params.get(REASON_FIELD) not in reasons:
        return env._("Please choose a tax exemption reason.")

    documents = [params[key] for key in document_keys if getattr(params[key], "filename", "")]
    if not documents:
        return env._("Please upload your tax exemption certificate.")
    for document in documents:
        extension = "." + document.filename.rsplit(".", 1)[-1].lower()
        content = document.stream.read(1024)
        document.stream.seek(0)
        if guess_mimetype(content) not in ALLOWED_DOCUMENTS.get(extension, ()):
            return env._("Your tax exemption certificate must be a PDF, JPG, PNG or BMP file.")
    return None


class IntTaxExemptionForm(WebsiteForm):

    @http.route()
    def website_form(self, model_name, **kwargs):
        if model_name == "crm.lead":
            error = int_tax_exemption_error(request.env, request.params)
            if error:
                return json.dumps({"error": error})
        return super().website_form(model_name, **kwargs)

    def insert_attachment(self, model_sudo, id_record, files):
        """Put each form upload on the lead's Documents tab, labelled by its form field."""
        is_lead = model_sudo.model == "crm.lead"
        field_labels = [getattr(file, "field_name", "") for file in files] if is_lead else []
        res = super().insert_attachment(model_sudo, id_record, files)
        if is_lead and files:
            int_documents_from_form(model_sudo.env, id_record, field_labels)
        return res


def int_documents_from_form(env, lead_id, field_labels):
    """Create a lead document for each attachment the form just added, in upload order.

    Odoo creates one attachment per uploaded file, in the order of ``files``, so the
    lead's new attachments line up with the field each file came from.
    """
    lead = env["crm.lead"].sudo().browse(lead_id).exists()
    if not lead:
        return
    Document = env["int.lead.document"].sudo().with_context(int_document_no_log=True)
    taken = Document.search([("lead_id", "=", lead.id)]).attachment_id
    attachments = env["ir.attachment"].sudo().search([
        ("res_model", "=", "crm.lead"),
        ("res_id", "=", lead.id),
        ("id", "not in", taken.ids),
    ], order="id")
    Label = env["int.lead.document.label"].sudo()
    for attachment, field_label in zip(attachments, field_labels):
        Document.create({
            "lead_id": lead.id,
            "label_id": Label._int_for_form_field(field_label).id,
            "attachment_id": attachment.id,
        })
