import base64

from odoo import api, fields, models
from odoo.exceptions import AccessError

from .dealer_certificate import ALLOWED_LOGOS, MAX_LOGO_BYTES, int_check_document, int_check_upload

AGREEMENT_LABEL = "dealer_agreement"


class IntLeadDocument(models.Model):
    _inherit = "int.lead.document"

    int_replaces_id = fields.Many2one(
        "int.lead.document",
        string="Replaces",
        readonly=True,
        index=True,
        ondelete="set null",
        help="The file a dealer replaced with this one from My Portal → Documents.",
    )

    def _int_portal_replace(self, user, filename, content):
        """A dealer replaces an application file. The new one goes on the same lead, under the
        same label, unreviewed; the dealer sees it in place of the old one, and staff see both."""
        self.ensure_one()
        if not user.int_portal_can("manage_certificates"):
            raise AccessError(self.env._("You can't change documents for this account."))
        int_check_document(self.env, filename, content)
        old = self.sudo()
        lead = old.lead_id
        attachment = self.env["ir.attachment"].sudo().create({
            "name": filename,
            "raw": content,
            "res_model": "crm.lead",
            "res_id": lead.id,
        })
        new = self.sudo().with_context(int_document_no_log=True).create({
            "lead_id": lead.id,
            "label_id": old.label_id.id,
            "attachment_id": attachment.id,
            "int_replaces_id": old.id,
        })
        lead._int_document_log(self.env._(
            "%(user)s replaced %(old)s with %(new)s under %(label)s from My Portal. The new file needs review.",
            user=user.name, old=old.name, new=new.name, label=old.label_id.name,
        ))
        if lead.user_id:
            lead.sudo().activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=lead.user_id.id,
                summary=self.env._("Review replaced document: %(label)s", label=old.label_id.name),
            )
        return new


class ResPartner(models.Model):
    _inherit = "res.partner"

    int_certificate_count = fields.Integer(compute="_compute_int_certificate_count", groups="base.group_user")

    def _compute_int_certificate_count(self):
        counts = dict(self.env["int.dealer.certificate"]._read_group(
            [("partner_id", "in", self.commercial_partner_id.ids), ("status", "not in", ("superseded", "rejected"))],
            ["partner_id"], ["__count"],
        ))
        for partner in self:
            partner.int_certificate_count = counts.get(partner.commercial_partner_id, 0)

    def _int_application_documents(self, company):
        """The lead documents of this dealer's applications for ``company``, newest file of each
        replacement chain only. The Dealer Agreement label is left out; it has its own slot."""
        commercial = self.commercial_partner_id
        leads = self.env["crm.lead"].sudo().with_context(active_test=False).search([
            ("partner_id", "child_of", commercial.id),
            ("company_id", "in", [company.id, False]),
        ])
        documents = self.env["int.lead.document"].sudo().search([("lead_id", "in", leads.ids)])
        agreement = self.env["int.lead.document.label"]._int_by_code(AGREEMENT_LABEL)
        replaced = documents.int_replaces_id
        return documents.filtered(lambda doc: doc.label_id != agreement and doc not in replaced)

    def _int_dealer_agreement(self, company):
        """The newest file under the Dealer Agreement label on this dealer's leads."""
        commercial = self.commercial_partner_id
        agreement = self.env["int.lead.document.label"]._int_by_code(AGREEMENT_LABEL)
        if not agreement:
            return self.env["int.lead.document"]
        leads = self.env["crm.lead"].sudo().with_context(active_test=False).search([
            ("partner_id", "child_of", commercial.id),
            ("company_id", "in", [company.id, False]),
        ])
        return self.env["int.lead.document"].sudo().search(
            [("lead_id", "in", leads.ids), ("label_id", "=", agreement.id)], order="id desc", limit=1,
        )

    def _int_portal_set_logo(self, user, filename, content):
        """The dealer's logo, on the company contact's image (``image_512`` and smaller are made from it)."""
        if not user.int_portal_can("manage_logo"):
            raise AccessError(self.env._("Only the account owner can change the logo."))
        int_check_upload(
            self.env, filename, content, ALLOWED_LOGOS, MAX_LOGO_BYTES,
            self.env._("Upload a PNG, JPG or WebP image."),
        )
        commercial = user.partner_id.commercial_partner_id.sudo()
        commercial.image_1920 = base64.b64encode(content)
        commercial.message_post(
            body=self.env._("%(user)s changed the logo from My Portal.", user=user.name),
            subtype_xmlid="mail.mt_note",
        )
        return commercial

    def action_int_view_certificates(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("int_crm_customizations.int_dealer_certificate_action")
        commercial = self.commercial_partner_id
        action["domain"] = [("partner_id", "=", commercial.id)]
        action["context"] = {"default_partner_id": commercial.id}
        return action


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _int_documents_page_ok(self, website):
        """Documents is for dealer portal logins: a dealer pricelist and a role that may view it."""
        user = self.env.user
        if user._is_public() or not user.share or not user.int_portal_can("view_documents"):
            return False
        return bool(self.env["product.template"]._int_is_dealer_contact(user.partner_id, website))
