import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

NOTIFY_ACTIVITY = ("activity_and_email", "activity_only")
NOTIFY_EMAIL = ("activity_and_email", "email_only")


class IntHelpdeskAlertList(models.Model):
    _name = "int.helpdesk.alert.list"
    _description = "Help & Feedback Alert List"
    _order = "company_id, code, id"

    name = fields.Char(required=True)
    code = fields.Selection(
        selection=[
            ("help_return", "Return"),
            ("help_warranty", "Warranty claim"),
            ("help_feedback", "Feedback"),
            ("help_part", "Part request"),
            ("help_general", "General inquiry"),
        ],
        required=True,
        help="Used by Help & Feedback when someone submits this kind of request. Leave the value that was created for the company.",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    user_ids = fields.Many2many(
        "res.users",
        "int_helpdesk_alert_list_user_rel",
        "alert_id",
        "user_id",
        string="Staff",
        domain=[("share", "=", False)],
        help="Internal people who are notified. Portal users are not listed.",
    )
    group_ids = fields.Many2many(
        "res.groups",
        "int_helpdesk_alert_list_group_rel",
        "alert_id",
        "group_id",
        string="Groups",
        help="Active internal users in these groups are notified too.",
    )
    extra_emails = fields.Char(
        string="Extra emails",
        help="Comma-separated inboxes, added to the staff email.",
    )
    notify_mode = fields.Selection(
        selection=[
            ("activity_and_email", "Activity and email"),
            ("email_only", "Email only"),
            ("activity_only", "Activity only"),
        ],
        required=True,
        default="activity_and_email",
    )

    _code_company_uniq = models.Constraint(
        "UNIQUE(code, company_id)",
        "This alert already exists for this company.",
    )

    def _int_recipient_users(self):
        """Ticked internal users, plus active internal users of the ticked groups."""
        self.ensure_one()
        users = self.user_ids.filtered(lambda user: user.active and not user.share)
        if self.group_ids:
            users |= self.env["res.users"].search([
                ("active", "=", True),
                ("share", "=", False),
                ("all_group_ids", "in", self.group_ids.ids),
            ])
        return users

    def _int_extra_emails(self):
        self.ensure_one()
        emails = []
        for part in (self.extra_emails or "").split(","):
            email = part.strip()
            if email:
                emails.append(email)
        return emails

    @api.model
    def _int_notify(self, code, record, summary, company):
        """Alert staff for one Help & Feedback ticket.

        Recipients are the list's users and groups. With nobody configured, fall
        back to the sale order's salesperson, or the company email, and log a
        warning. One email goes out, with the addresses passed at send time so
        staff can edit the template wording without freezing a recipient.
        """
        record = record.sudo()
        company = company.sudo()
        alert = self.sudo().search([
            ("code", "=", code),
            ("company_id", "=", company.id),
        ], limit=1)
        users = alert._int_recipient_users() if alert else self.env["res.users"]
        extra = alert._int_extra_emails() if alert else []
        mode = alert.notify_mode if alert else "activity_and_email"
        if not users and not extra:
            users, extra = self._int_notify_fallback(code, record, company)
        summary = summary or record.display_name
        if mode in NOTIFY_ACTIVITY and users:
            self._int_notify_activities(record, users, summary)
        if mode in NOTIFY_EMAIL:
            emails = self._int_work_emails(users) + extra
            self._int_notify_email(record, emails)
        if users.partner_id:
            try:
                record.message_subscribe(partner_ids=users.partner_id.ids)
            except Exception:
                _logger.exception(
                    "Help & Feedback could not subscribe staff on ticket %s.", record.id,
                )
        if len(users) == 1 and "user_id" in record._fields and not record.user_id:
            try:
                record.write({"user_id": users.id})
            except Exception:
                _logger.exception(
                    "Help & Feedback could not assign ticket %s.", record.id,
                )

    @api.model
    def _int_notify_fallback(self, code, record, company):
        salesperson = self.env["res.users"]
        if "sale_order_id" in record._fields and record.sale_order_id:
            candidate = record.sale_order_id.user_id
            if candidate and candidate.active and not candidate.share:
                salesperson = candidate
        if salesperson:
            _logger.warning(
                "Help & Feedback alert %s for %s has no recipients. Using salesperson %s.",
                code, company.display_name, salesperson.display_name,
            )
            return salesperson, []
        email = (company.email or "").strip()
        _logger.warning(
            "Help & Feedback alert %s for %s has no recipients. Using %s.",
            code, company.display_name, email or "no company email",
        )
        return self.env["res.users"], ([email] if email else [])

    @api.model
    def _int_work_emails(self, users):
        emails = []
        seen = set()
        for user in users:
            email = (user.email or "").strip()
            key = email.lower()
            if email and key not in seen:
                seen.add(key)
                emails.append(email)
        return emails

    @api.model
    def _int_notify_activities(self, record, users, summary):
        if not self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False):
            _logger.warning("Help & Feedback skipped activities because the To-Do type is missing.")
            return
        today = fields.Date.context_today(record)
        for user in users:
            try:
                record.activity_schedule(
                    "mail.mail_activity_data_todo",
                    date_deadline=today,
                    summary=summary,
                    user_id=user.id,
                )
            except Exception:
                _logger.exception(
                    "Help & Feedback could not schedule an activity on ticket %s for %s.",
                    record.id, user.display_name,
                )

    @api.model
    def _int_notify_email(self, record, emails):
        unique = []
        seen = set()
        for email in emails:
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(email)
        if not unique:
            return
        template = self.env.ref(
            "int_helpdesk_customizations.mail_template_help_alert",
            raise_if_not_found=False,
        )
        if not template:
            _logger.warning("Help & Feedback staff email template is missing.")
            return
        try:
            template.sudo().send_mail(
                record.id,
                force_send=False,
                email_values={"email_to": ", ".join(unique)},
            )
        except Exception:
            _logger.exception("Help & Feedback could not email staff about ticket %s.", record.id)
