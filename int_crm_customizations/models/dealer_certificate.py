import base64

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tools.mimetypes import guess_mimetype

from .crm_lead import GRANT_GROUPS

CERT_TYPES = [
    ("resale", "Resale Certificate"),
    ("sales_tax_exemption", "Sales Tax Exemption"),
    ("business_license", "Business License"),
    ("other", "Other"),
]
STATUSES = [
    ("pending_review", "Pending Review"),
    ("valid", "Valid"),
    ("expiring", "Expiring Soon"),
    ("expired", "Expired"),
    ("superseded", "Replaced"),
    ("rejected", "Rejected"),
]
CURRENT = ("valid", "expiring")
# Statuses a dealer can replace from My Portal.
REPLACEABLE = ("valid", "expiring", "expired")
# Approving one of these also refreshes the contact's Tax Exemption Certificate file.
TAX_TYPES = ("resale", "sales_tax_exemption")
DEFAULT_REMINDER_DAYS = "60,30,7"

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
# Extension -> content types it may be detected as. Older libmagic calls BMP image/x-ms-bmp.
ALLOWED_DOCUMENTS = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".bmp": {"image/bmp", "image/x-ms-bmp"},
}
MAX_LOGO_BYTES = 5 * 1024 * 1024
# No SVG: it can carry scripts.
ALLOWED_LOGOS = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
}


def int_check_upload(env, filename, content, allowed, max_bytes, type_error):
    """Refuse an empty, oversized or mistyped upload. Checks both the extension and the content."""
    if not filename or not content:
        raise UserError(env._("Choose a file to upload."))
    if len(content) > max_bytes:
        raise UserError(env._("The file is larger than %(mb)s MB.", mb=max_bytes // (1024 * 1024)))
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if guess_mimetype(content) not in allowed.get(extension, ()):
        raise UserError(type_error)


def int_check_document(env, filename, content):
    int_check_upload(
        env, filename, content, ALLOWED_DOCUMENTS, MAX_DOCUMENT_BYTES,
        env._("Upload a PDF, JPG, PNG or BMP file."),
    )


def int_can_review_certificates(env):
    return env.su or any(env.user.has_group(group) for group in GRANT_GROUPS)


class IntDealerCertificate(models.Model):
    _name = "int.dealer.certificate"
    _description = "Dealer Certificate"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "partner_id, cert_type, state_id, id desc"

    partner_id = fields.Many2one(
        "res.partner", string="Dealer", required=True, index=True, ondelete="cascade", tracking=True,
        help="The dealer's company contact.",
    )
    company_id = fields.Many2one(
        "res.company", required=True, index=True, default=lambda self: self.env.company,
    )
    cert_type = fields.Selection(CERT_TYPES, string="Type", required=True, tracking=True)
    state_id = fields.Many2one("res.country.state", string="Issuing State", tracking=True)
    cert_number = fields.Char(string="Number", tracking=True)
    issue_date = fields.Date()
    expiration_date = fields.Date(tracking=True, help="Leave empty when the certificate doesn't expire.")
    # Not required on the field so the form can take an upload; create always sets it.
    attachment_id = fields.Many2one("ir.attachment", string="File", ondelete="restrict")
    file_name = fields.Char(related="attachment_id.name")
    status = fields.Selection(
        STATUSES, default="pending_review", required=True, readonly=True, index=True, tracking=True,
    )
    replaces_id = fields.Many2one("int.dealer.certificate", string="Replaces", readonly=True, index=True, ondelete="set null")
    replaced_by_id = fields.Many2one("int.dealer.certificate", string="Replaced By", readonly=True, ondelete="set null")
    submitted_by_id = fields.Many2one("res.users", string="Submitted By", readonly=True, default=lambda self: self.env.user)
    reviewed_by_id = fields.Many2one("res.users", string="Reviewed By", readonly=True)
    reviewed_on = fields.Datetime(readonly=True)
    review_note = fields.Text(string="Rejection Note", help="Needed to reject. It's emailed to the dealer.")
    reminder_sent_days = fields.Char(
        readonly=True, copy=False, help="Reminder thresholds already emailed, in days before expiry.",
    )
    # Staff upload the file here from the form; create turns it into the attachment.
    upload = fields.Binary(store=False)
    upload_name = fields.Char(store=False)

    @api.depends("cert_type", "state_id", "cert_number")
    def _compute_display_name(self):
        labels = dict(CERT_TYPES)
        for cert in self:
            parts = [labels.get(cert.cert_type, ""), cert.state_id.code or "", cert.cert_number or ""]
            cert.display_name = " · ".join(part for part in parts if part)

    @api.constrains("status", "partner_id", "company_id", "cert_type", "state_id")
    def _check_one_current(self):
        """One current and one pending certificate per dealer, type and state. Other is not limited."""
        for cert in self.filtered(lambda item: item.cert_type != "other"):
            for group in (CURRENT, ("pending_review",)):
                if cert.status not in group:
                    continue
                clash = self.search_count([
                    ("id", "!=", cert.id),
                    ("partner_id", "=", cert.partner_id.id),
                    ("company_id", "=", cert.company_id.id),
                    ("cert_type", "=", cert.cert_type),
                    ("state_id", "=", cert.state_id.id),
                    ("status", "in", group),
                ], limit=1)
                if clash:
                    raise ValidationError(self.env._(
                        "%(dealer)s already has a %(status)s %(type)s for this state.",
                        dealer=cert.partner_id.display_name,
                        status=dict(STATUSES)[cert.status].lower(),
                        type=dict(CERT_TYPES)[cert.cert_type],
                    ))

    @api.model_create_multi
    def create(self, vals_list):
        uploads = []
        for vals in vals_list:
            upload = vals.pop("upload", False)
            upload_name = vals.pop("upload_name", False)
            uploads.append((upload, upload_name))
            if not vals.get("attachment_id"):
                if not upload:
                    raise UserError(self.env._("Choose a file to upload."))
                vals["attachment_id"] = self.env["ir.attachment"].sudo().create({
                    "name": upload_name or self.env._("Certificate"),
                    "datas": upload,
                    "res_model": self._name,
                }).id
        certs = super().create(vals_list)
        for cert in certs:
            attachment = cert.sudo().attachment_id
            if attachment.res_model == self._name and not attachment.res_id:
                attachment.res_id = cert.id
        return certs

    # Portal

    @api.model
    def _int_dealer_certificates(self, partner, company):
        """What My Portal → Documents lists for the dealer: everything not replaced or rejected."""
        commercial = partner.commercial_partner_id
        return self.sudo().search([
            ("partner_id", "=", commercial.id),
            ("company_id", "=", company.id),
            ("status", "not in", ("superseded", "rejected")),
        ])

    @api.model
    def _int_portal_submit(self, user, company, values, filename, content, replaces=None):
        """Add a certificate, or replace one, from My Portal. It waits for staff review.

        ``values`` holds cert_type, state_id, cert_number, issue_date and expiration_date
        as posted. A replacement keeps the old certificate's type and state; the old one
        stays current until staff approve the new one.
        """
        if not user.int_portal_can("manage_certificates"):
            raise AccessError(self.env._("You can't change certificates for this account."))
        commercial = user.partner_id.commercial_partner_id
        int_check_document(self.env, filename, content)
        if replaces:
            replaces = replaces.sudo()
            if replaces.partner_id != commercial or replaces.company_id != company:
                raise AccessError(self.env._("That certificate isn't on your account."))
            if replaces.status not in REPLACEABLE:
                raise UserError(self.env._("That certificate can't be replaced."))
            if replaces.replaced_by_id.status == "pending_review":
                raise UserError(self.env._("A replacement for that certificate is already waiting for review."))
            cert_type, state = replaces.cert_type, replaces.state_id
        else:
            cert_type = values.get("cert_type")
            if cert_type not in dict(CERT_TYPES):
                raise UserError(self.env._("Choose a certificate type."))
            state = self.env["res.country.state"]
            if str(values.get("state_id") or "").isdigit():
                state = state.browse(int(values["state_id"])).exists()
            if cert_type != "other":
                current = self._int_dealer_certificates(commercial, company).filtered(
                    lambda cert: cert.cert_type == cert_type and cert.state_id == state
                )
                if current:
                    raise UserError(self.env._(
                        "You already have this certificate for that state. Use Replace on it instead."
                    ))
        issue_date = self._int_parse_date(values.get("issue_date"))
        expiration_date = self._int_parse_date(values.get("expiration_date"))
        if issue_date and expiration_date and expiration_date < issue_date:
            raise UserError(self.env._("The expiration date is before the issue date."))
        attachment = self.env["ir.attachment"].sudo().create({
            "name": filename,
            "raw": content,
            "res_model": self._name,
        })
        cert = self.sudo().create({
            "partner_id": commercial.id,
            "company_id": company.id,
            "cert_type": cert_type,
            "state_id": state.id,
            "cert_number": (values.get("cert_number") or "").strip()[:64] or False,
            "issue_date": issue_date,
            "expiration_date": expiration_date,
            "attachment_id": attachment.id,
            "replaces_id": replaces.id if replaces else False,
            "submitted_by_id": user.id,
        })
        if replaces:
            replaces.replaced_by_id = cert
        cert._int_request_review(user)
        return cert

    def _int_parse_date(self, value):
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except ValueError:
            raise UserError(self.env._("Enter dates as YYYY-MM-DD."))

    # Staff review

    def _int_reviewer(self):
        """The dealer's salesperson, else the reviewer set in Settings."""
        self.ensure_one()
        salesperson = self.partner_id.user_id
        if salesperson and salesperson.active and not salesperson.share:
            return salesperson
        return self.company_id.int_cert_reviewer_id

    def _int_request_review(self, user):
        for cert in self.sudo():
            body = self.env._(
                "%(user)s submitted this from My Portal. Review it, then Approve or Reject.",
                user=user.name,
            ) if not cert.replaces_id else self.env._(
                "%(user)s submitted this from My Portal to replace %(old)s. The old one stays valid until you approve this one.",
                user=user.name, old=cert.replaces_id.display_name,
            )
            cert.message_post(body=body, subtype_xmlid="mail.mt_note")
            reviewer = cert._int_reviewer()
            if reviewer:
                cert.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=reviewer.id,
                    summary=self.env._("Review dealer certificate"),
                )

    def _int_check_reviewer(self):
        if not int_can_review_certificates(self.env):
            raise AccessError(self.env._("Only sales managers and invoicing users can review certificates."))

    def _int_dated_status(self):
        """valid, expiring or expired, from the expiration date and the first reminder window."""
        self.ensure_one()
        if not self.expiration_date:
            return "valid"
        days_left = (self.expiration_date - fields.Date.context_today(self)).days
        if days_left < 0:
            return "expired"
        windows = self.company_id._int_cert_reminder_days()
        return "expiring" if windows and days_left <= windows[0] else "valid"

    def _int_close_review(self, feedback):
        todo = self.env.ref("mail.mail_activity_data_todo")
        self.sudo().activity_ids.filtered(lambda act: act.activity_type_id == todo).action_feedback(feedback=feedback)

    def action_approve(self):
        self._int_check_reviewer()
        for cert in self:
            if cert.status != "pending_review":
                raise UserError(self.env._("Only a certificate waiting for review can be approved."))
            old = cert.replaces_id
            if old and old.status in REPLACEABLE:
                old.status = "superseded"
            cert.write({
                "status": cert._int_dated_status(),
                "reviewed_by_id": self.env.user.id,
                "reviewed_on": fields.Datetime.now(),
                "reminder_sent_days": False,
            })
            cert._int_close_review(self.env._("Approved"))
            cert._int_copy_to_contact()
        return True

    def action_reject(self):
        self._int_check_reviewer()
        for cert in self:
            if cert.status != "pending_review":
                raise UserError(self.env._("Only a certificate waiting for review can be rejected."))
            if not (cert.review_note or "").strip():
                raise UserError(self.env._("Write a rejection note first. It's emailed to the dealer."))
            cert.write({
                "status": "rejected",
                "reviewed_by_id": self.env.user.id,
                "reviewed_on": fields.Datetime.now(),
            })
            if cert.replaces_id.replaced_by_id == cert:
                cert.replaces_id.replaced_by_id = False
            cert._int_close_review(self.env._("Rejected"))
            cert._int_send("int_crm_customizations.mail_cert_rejected")
        return True

    def action_view_file(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.attachment_id.id}",
            "target": "new",
        }

    def _int_copy_to_contact(self):
        """A tax-exempt dealer's approved tax or resale certificate becomes the contact's file.

        It only refreshes the file. Exemption and fiscal position stay staff decisions.
        """
        self.ensure_one()
        partner = self.partner_id.sudo().with_company(self.company_id)
        if self.cert_type not in TAX_TYPES or not partner.x_is_tax_exempt:
            return
        attachment = self.sudo().with_context(bin_size=False).attachment_id
        partner.write({
            "x_tax_exemption_document": base64.b64encode(attachment.raw) if attachment.raw else False,
            "x_tax_exemption_document_filename": attachment.name,
        })

    # Emails and reminders

    def _int_dealer_recipients(self):
        """Owner and Accountant logins with an email, else the company contact's email."""
        self.ensure_one()
        partner = self.partner_id
        users = partner._int_portal_family_users().filtered(
            lambda user: user.active and user.int_portal_role_value() in ("owner", "accountant")
        )
        return users.partner_id.filtered("email") or partner.filtered("email")

    def _int_send(self, template_xmlid):
        template = self.env.ref(template_xmlid).sudo()
        for cert in self:
            recipients = cert._int_dealer_recipients()
            if recipients:
                template.send_mail(cert.id, email_values={"recipient_ids": [Command.set(recipients.ids)]})

    def _int_notify_staff(self, body, activity_summary=False):
        self.ensure_one()
        reviewer = self._int_reviewer()
        self.sudo().message_post(
            body=body,
            subtype_xmlid="mail.mt_note",
            partner_ids=reviewer.partner_id.ids,
        )
        if activity_summary and reviewer:
            self.sudo().activity_schedule("mail.mail_activity_data_todo", user_id=reviewer.id, summary=activity_summary)

    @api.model
    def _int_cron_certificates(self):
        """Daily: email each reminder threshold once, and expire certificates the day after they run out."""
        today = fields.Date.context_today(self)
        for cert in self.sudo().search([("status", "in", CURRENT), ("expiration_date", "!=", False)]):
            days_left = (cert.expiration_date - today).days
            if days_left < 0:
                cert.status = "expired"
                cert._int_send("int_crm_customizations.mail_cert_expired")
                cert._int_notify_staff(
                    self.env._("This certificate expired. Ordering isn't blocked; decide on the dealer's tax treatment."),
                    self.env._("Dealer certificate expired"),
                )
                continue
            windows = cert.company_id._int_cert_reminder_days()
            sent = {int(day) for day in (cert.reminder_sent_days or "").split(",") if day.strip().isdigit()}
            due = [day for day in windows if days_left <= day and day not in sent]
            if due:
                cert._int_send("int_crm_customizations.mail_cert_expiring")
                cert.reminder_sent_days = ",".join(str(day) for day in sorted(sent | set(due), reverse=True))
                cert._int_notify_staff(self.env._(
                    "Expiry reminder sent to the dealer: %(days)s days left.", days=days_left,
                ))
            if cert.status == "valid" and windows and days_left <= windows[0]:
                cert.status = "expiring"
