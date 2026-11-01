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


class IntTaxExemptionForm(WebsiteForm):

    def _int_tax_exemption_error(self):
        """Check the claim, and drop what a dealer filled in before unticking the box."""
        params = request.params
        # The website form sends a file under an indexed name, like field[0][0].
        document_keys = [key for key in params if key.split("[", 1)[0] == DOCUMENT_FIELD]
        if not params.get("x_is_tax_exempt"):
            params.pop(REASON_FIELD, None)
            for key in document_keys:
                params.pop(key)
            return None

        reasons = request.env["crm.lead"]._fields[REASON_FIELD].get_values(request.env)
        if params.get(REASON_FIELD) not in reasons:
            return request.env._("Please choose a tax exemption reason.")

        documents = [params[key] for key in document_keys if getattr(params[key], "filename", "")]
        if not documents:
            return request.env._("Please upload your tax exemption certificate.")
        for document in documents:
            extension = "." + document.filename.rsplit(".", 1)[-1].lower()
            content = document.stream.read(1024)
            document.stream.seek(0)
            if ALLOWED_DOCUMENTS.get(extension) != guess_mimetype(content):
                return request.env._("Your tax exemption certificate must be a PDF, JPG or PNG file.")
        return None

    @http.route()
    def website_form(self, model_name, **kwargs):
        if model_name == "crm.lead":
            error = self._int_tax_exemption_error()
            if error:
                return json.dumps({"error": error})
        return super().website_form(model_name, **kwargs)
