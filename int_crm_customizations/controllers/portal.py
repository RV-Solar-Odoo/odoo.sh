from itertools import groupby
from urllib.parse import quote

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request, route
from odoo.tools.image import image_data_uri

from ..models.dealer_certificate import CERT_TYPES, MAX_DOCUMENT_BYTES, MAX_LOGO_BYTES, REPLACEABLE

DONE_MESSAGES = {
    "certificate": "Thanks. Your certificate is waiting for our review.",
    "replaced": "Thanks. We'll review the new file.",
    "logo": "Your logo is saved.",
}


class IntDealerDocuments(http.Controller):

    def _int_dealer(self):
        """The logged-in dealer's company contact, or None when Documents isn't theirs to see."""
        if not request.env["res.users"]._int_documents_page_ok(request.website):
            return None
        return request.env.user.partner_id.commercial_partner_id

    def _int_upload(self, max_bytes):
        """(filename, content) of the posted file, reading one byte past the limit so a
        large file is refused without loading all of it."""
        upload = request.httprequest.files.get("file")
        if not upload or not upload.filename:
            return "", b""
        return upload.filename, upload.read(max_bytes + 1)

    def _int_back(self, error=None, done=None):
        if error:
            return request.redirect("/my/documents?error=%s" % quote(error))
        return request.redirect("/my/documents?done=%s" % done if done else "/my/documents")

    @route("/my/documents", type="http", auth="user", website=True)
    def int_dealer_documents(self, **kwargs):
        dealer = self._int_dealer()
        if not dealer:
            return request.redirect("/my")
        user = request.env.user
        company = request.website.company_id
        documents = dealer._int_application_documents(company)
        groups = [
            (label, list(docs))
            for label, docs in groupby(documents.sorted(lambda doc: (doc.label_sequence, doc.label_id.id, doc.id)), key=lambda doc: doc.label_id)
        ]
        certificates = request.env["int.dealer.certificate"]._int_dealer_certificates(dealer, company)
        country = dealer.country_id or request.env.ref("base.us")
        image = dealer.sudo().image_256
        return request.render("int_crm_customizations.portal_dealer_documents", {
            "page_name": "int_documents",
            "int_dealer": dealer,
            "int_groups": groups,
            "int_certificates": certificates,
            "int_cert_types": CERT_TYPES,
            "int_replaceable": REPLACEABLE,
            "int_states": request.env["res.country.state"].sudo().search([("country_id", "=", country.id)]),
            "int_logo": image_data_uri(image) if image and dealer.sudo().image_1920 else False,
            "int_agreement": dealer._int_dealer_agreement(company),
            "int_can_manage": user.int_portal_can("manage_certificates"),
            "int_can_logo": user.int_portal_can("manage_logo"),
            "int_error": kwargs.get("error") or "",
            "int_done": DONE_MESSAGES.get(kwargs.get("done"), ""),
        })

    @route("/my/documents/file/<string:kind>/<int:record_id>", type="http", auth="user", website=True)
    def int_dealer_document_file(self, kind, record_id, download=None, **kwargs):
        """One of the dealer's own files. Anything else is a 404, so ids can't be probed."""
        dealer = self._int_dealer()
        if not dealer:
            return request.not_found()
        company = request.website.company_id
        attachment = None
        if kind == "application":
            allowed = dealer._int_application_documents(company) | dealer._int_dealer_agreement(company)
            document = allowed.filtered(lambda doc: doc.id == record_id)
            attachment = document.attachment_id
        elif kind == "certificate":
            certificates = request.env["int.dealer.certificate"].sudo().search([
                ("id", "=", record_id),
                ("partner_id", "=", dealer.id),
                ("company_id", "=", company.id),
            ], limit=1)
            attachment = certificates.attachment_id
        if not attachment:
            return request.not_found()
        return request.env["ir.binary"]._get_stream_from(attachment.sudo()).get_response(as_attachment=bool(download))

    @route("/my/documents/application/<int:document_id>/replace", type="http", auth="user", website=True, methods=["POST"])
    def int_dealer_document_replace(self, document_id, **kwargs):
        dealer = self._int_dealer()
        if not dealer:
            return request.redirect("/my")
        document = dealer._int_application_documents(request.website.company_id).filtered(lambda doc: doc.id == document_id)
        if not document:
            return request.not_found()
        filename, content = self._int_upload(MAX_DOCUMENT_BYTES)
        try:
            with request.env.cr.savepoint():
                document._int_portal_replace(request.env.user, filename, content)
        except (UserError, AccessError) as exc:
            return self._int_back(error=str(exc.args[0]))
        return self._int_back(done="replaced")

    @route("/my/documents/certificates", type="http", auth="user", website=True, methods=["POST"])
    def int_dealer_certificate_add(self, **post):
        return self._int_certificate_submit(post)

    @route("/my/documents/certificates/<int:certificate_id>/replace", type="http", auth="user", website=True, methods=["POST"])
    def int_dealer_certificate_replace(self, certificate_id, **post):
        dealer = self._int_dealer()
        if not dealer:
            return request.redirect("/my")
        replaces = request.env["int.dealer.certificate"]._int_dealer_certificates(dealer, request.website.company_id).filtered(
            lambda cert: cert.id == certificate_id
        )
        if not replaces:
            return request.not_found()
        return self._int_certificate_submit(post, replaces)

    def _int_certificate_submit(self, post, replaces=None):
        if not self._int_dealer():
            return request.redirect("/my")
        filename, content = self._int_upload(MAX_DOCUMENT_BYTES)
        try:
            with request.env.cr.savepoint():
                request.env["int.dealer.certificate"]._int_portal_submit(
                    request.env.user, request.website.company_id, post, filename, content, replaces=replaces,
                )
        except (UserError, AccessError, ValidationError) as exc:
            return self._int_back(error=str(exc.args[0]))
        return self._int_back(done="replaced" if replaces else "certificate")

    @route("/my/documents/logo", type="http", auth="user", website=True, methods=["POST"])
    def int_dealer_logo(self, **kwargs):
        dealer = self._int_dealer()
        if not dealer:
            return request.redirect("/my")
        filename, content = self._int_upload(MAX_LOGO_BYTES)
        try:
            with request.env.cr.savepoint():
                dealer._int_portal_set_logo(request.env.user, filename, content)
        except (UserError, AccessError) as exc:
            return self._int_back(error=str(exc.args[0]))
        return self._int_back(done="logo")
