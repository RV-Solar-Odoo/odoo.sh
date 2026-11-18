import base64

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import format_datetime

# Who may delete a lead document, from the Documents tab or the chatter's Files.
DELETE_GROUPS = ("sales_team.group_sale_manager", "base.group_system")

# Website form upload labels that belong under a starting label, compared lowercased.
LABEL_ALIASES = {
    "business_license": {"copy of business license", "business license"},
    "tax_certificate": {"tax exemption certificate", "exemption certificate", "resale certificate"},
    "storefront": {"business storefront + interior", "business storefront", "storefront"},
}


def int_can_delete_documents(env):
    return env.su or any(env.user.has_group(group) for group in DELETE_GROUPS)


class IntLeadDocumentLabel(models.Model):
    _name = "int.lead.document.label"
    _description = "Lead Document Label"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=50)
    active = fields.Boolean(default=True)
    code = fields.Char(
        readonly=True,
        copy=False,
        help="Set on the starting labels so the code can find them after a rename.",
    )

    _code_unique = models.Constraint("UNIQUE(code)", "Each label code is used once.")

    @api.model
    def _int_by_code(self, code):
        return self.with_context(active_test=False).search([("code", "=", code)], limit=1)

    @api.model
    def _int_for_form_field(self, field_label):
        """The label for a website form upload field, created when no label matches."""
        clean = " ".join((field_label or "").split())
        if not clean:
            return self._int_by_code("other")
        lowered = clean.lower()
        for code, aliases in LABEL_ALIASES.items():
            if lowered in aliases:
                label = self._int_by_code(code)
                if label:
                    return label
        Label = self.sudo().with_context(active_test=False)
        label = Label.search([("name", "=ilike", clean)], limit=1)
        return label or Label.create({"name": clean})


class IntLeadDocument(models.Model):
    _name = "int.lead.document"
    _description = "Lead Document"
    _order = "label_sequence, label_id, id"

    lead_id = fields.Many2one("crm.lead", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="lead_id.company_id", store=True)
    label_id = fields.Many2one("int.lead.document.label", string="Label", required=True, ondelete="restrict")
    label_sequence = fields.Integer(related="label_id.sequence", store=True)
    attachment_id = fields.Many2one("ir.attachment", required=True, ondelete="cascade", index=True)
    name = fields.Char(related="attachment_id.name", string="File Name")
    mimetype = fields.Char(related="attachment_id.mimetype")
    checksum = fields.Char(related="attachment_id.checksum")
    reviewed = fields.Boolean()
    reviewed_by_id = fields.Many2one("res.users", string="Reviewed By", readonly=True)
    reviewed_on = fields.Datetime(readonly=True)
    review_note = fields.Char(compute="_compute_review_note")
    partner_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Copy on Contact",
        readonly=True,
        copy=False,
        ondelete="set null",
        help="The copy made on the dealer's company contact.",
    )
    # Upload Document sends the file here; create turns it into the attachment.
    upload = fields.Binary(store=False)
    upload_name = fields.Char(store=False)

    @api.depends("reviewed", "reviewed_by_id", "reviewed_on")
    def _compute_review_note(self):
        for document in self:
            if not document.reviewed:
                document.review_note = False
                continue
            when = format_datetime(self.env, document.reviewed_on, dt_format="short") if document.reviewed_on else ""
            who = document.reviewed_by_id.name or ""
            document.review_note = " · ".join(part for part in (who, when) if part)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            upload = vals.pop("upload", False)
            upload_name = vals.pop("upload_name", False)
            if vals.get("attachment_id"):
                continue
            if not upload:
                raise UserError(self.env._("Choose a file to upload."))
            lead = self.env["crm.lead"].browse(vals.get("lead_id")).exists()
            if not lead:
                raise UserError(self.env._("Save the lead before adding documents."))
            lead.check_access("write")
            attachment = self.env["ir.attachment"].sudo().create({
                "name": upload_name or self.env._("Document"),
                "datas": upload,
                "res_model": "crm.lead",
                "res_id": lead.id,
            })
            vals["attachment_id"] = attachment.id
        documents = super().create(vals_list)
        if not self.env.context.get("int_document_no_log"):
            for document in documents.filtered(lambda doc: not doc.env.su):
                document.lead_id._int_document_log(self.env._(
                    "%(user)s added %(file)s under %(label)s.",
                    user=self.env.user.name,
                    file=document.name,
                    label=document.label_id.name,
                ))
        return documents

    def write(self, vals):
        if "reviewed" in vals:
            vals = dict(vals)
            if vals["reviewed"]:
                vals.update(reviewed_by_id=self.env.user.id, reviewed_on=fields.Datetime.now())
            else:
                vals.update(reviewed_by_id=False, reviewed_on=False)
        changed = self.filtered(lambda doc: "reviewed" in vals and doc.reviewed != bool(vals["reviewed"]))
        old_labels = {doc.id: doc.label_id for doc in self} if "label_id" in vals else {}
        res = super().write(vals)
        if self.env.context.get("int_document_no_log"):
            return res
        for document in changed:
            message = self.env._(
                "%(user)s marked %(label)s (%(file)s) as reviewed.",
                user=self.env.user.name, label=document.label_id.name, file=document.name,
            ) if document.reviewed else self.env._(
                "%(user)s unmarked %(label)s (%(file)s) as reviewed.",
                user=self.env.user.name, label=document.label_id.name, file=document.name,
            )
            document.lead_id._int_document_log(message)
        for document in self.filtered(lambda doc: doc.id in old_labels and old_labels[doc.id] != doc.label_id):
            document.lead_id._int_document_log(self.env._(
                "%(user)s moved %(file)s from %(old)s to %(new)s.",
                user=self.env.user.name,
                file=document.name,
                old=old_labels[document.id].name,
                new=document.label_id.name,
            ))
        return res

    def unlink(self):
        if not int_can_delete_documents(self.env):
            raise AccessError(self.env._("Only sales managers and administrators can delete documents."))
        attachments = self.sudo().attachment_id
        notes = [(doc.lead_id, doc.label_id.name, doc.name) for doc in self]
        res = super().unlink()
        attachments.exists().unlink()
        for lead, label, name in notes:
            if lead.exists():
                lead._int_document_log(self.env._(
                    "%(user)s deleted %(file)s from %(label)s.",
                    user=self.env.user.name, file=name, label=label,
                ))
        return res

    def action_int_copy_to_contact(self):
        """Copy reviewed documents to the lead's company contact."""
        leads = self.lead_id
        for lead in leads:
            partner = lead.partner_id.commercial_partner_id
            if not partner:
                raise UserError(self.env._("Link a contact to %(lead)s before copying documents.", lead=lead.name))
            lead._int_copy_documents_to_partner(partner, self.filtered(lambda doc: doc.lead_id == lead))
        return True

    def _int_copy_to_partner(self, partner):
        """Copy each reviewed, not yet copied document onto partner. Returns the copied ones."""
        copied = self.browse()
        for document in self.sudo().with_context(bin_size=False):
            if not document.reviewed:
                continue
            if document.partner_attachment_id and document.partner_attachment_id.res_id == partner.id:
                continue
            source = document.attachment_id
            copy = self.env["ir.attachment"].sudo().create({
                "name": f"{document.label_id.name} – {source.name}",
                "raw": source.raw,
                "mimetype": source.mimetype,
                "res_model": "res.partner",
                "res_id": partner.id,
            })
            document.with_context(int_document_no_log=True).partner_attachment_id = copy
            copied |= document
        return copied

    def _int_datas(self):
        """The file as base64, for the contact's Tax Exemption Certificate field."""
        self.ensure_one()
        raw = self.sudo().attachment_id.raw
        return base64.b64encode(raw) if raw else False


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def unlink(self):
        if self and not int_can_delete_documents(self.env):
            linked = self.env["int.lead.document"].sudo().search_count([("attachment_id", "in", self.ids)], limit=1)
            if linked:
                raise AccessError(self.env._(
                    "This file is on a lead's Documents tab. Only sales managers and administrators can delete it."
                ))
        return super().unlink()
