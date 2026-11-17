import json

from odoo import http
from odoo.http import request
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.website.controllers.form import WebsiteForm

REASON_FIELD = "x_tax_exemption_reason"
DOCUMENT_FIELD = "x_tax_exemption_document"
ALLOWED_DOCUMENTS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
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
    # The website form sends a file under an indexed name, like field[0][0].
    document_keys = [key for key in params if _int_base_name(key) == DOCUMENT_FIELD]
    if not params.get("x_is_tax_exempt"):
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
        if ALLOWED_DOCUMENTS.get(extension) != guess_mimetype(content):
            return env._("Your tax exemption certificate must be a PDF, JPG or PNG file.")
    return None


class IntTaxExemptionForm(WebsiteForm):

    @http.route()
    def website_form(self, model_name, **kwargs):
        if model_name == "crm.lead":
            error = int_tax_exemption_error(request.env, request.params)
            if error:
                return json.dumps({"error": error})
        return super().website_form(model_name, **kwargs)
