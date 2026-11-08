from odoo import _, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import email_normalize

SIGN_IN_TEMPLATE = "int_contacts_customizations.mail_template_dealer_sign_in"
SET_PASSWORD_TEMPLATE = "auth_signup.portal_set_password_email"


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_int_send_dealer_account_email(self):
        """Email this contact a create-password link, or a sign-in note if they already have one."""
        self.ensure_one()
        self._int_check_dealer_account_email_access()
        code, user, owner = self._int_send_dealer_account_email()
        title, message, level = self._int_dealer_account_email_notice(code, user, owner)
        self.message_post(body=message, subtype_xmlid="mail.mt_note")
        if owner != self:
            owner.message_post(body=message, subtype_xmlid="mail.mt_note")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": level,
                "sticky": level == "warning",
            },
        }

    def _int_check_dealer_account_email_access(self):
        if self.env.su or self.env.user.has_group("sales_team.group_sale_salesman"):
            return
        raise AccessError(_("Only sales users can send a dealer account email."))

    def _int_send_dealer_account_email(self):
        """Create or reuse the portal login for this contact's email.

        Returns ``(code, user, account_owner)``. ``code`` is ``created``,
        ``resent``, ``existing``, or ``other_contact``.
        """
        self.ensure_one()
        email = email_normalize(self.email or "")
        if not email:
            raise UserError(_("Add an email address before sending the account email."))
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        user = Users.search(Users._get_login_domain(email), limit=1)
        if not user:
            user = Users.search(Users._get_email_domain(email), limit=1)
        if user and user._is_internal():
            raise UserError(_("This email belongs to an internal user. No portal account was created."))

        family = self.commercial_partner_id | self.commercial_partner_id.child_ids
        if user and user.partner_id not in family:
            self._int_email_dealer_account(user)
            return "other_contact", user, user.partner_id

        if not user:
            user = self._int_create_portal_user(email)
            self._int_email_dealer_account(user)
            return "created", user, self

        if not user.active:
            user.active = True
        if not user._is_portal():
            portal = self.env.ref("base.group_portal")
            public = self.env.ref("base.group_public")
            user.write({"group_ids": [(4, portal.id), (3, public.id)]})
        self._int_email_dealer_account(user)
        if user.login_date:
            return "existing", user, user.partner_id
        return "resent", user, user.partner_id

    def _int_create_portal_user(self, email):
        company = self.company_id or self.env.company
        return self.env["res.users"].sudo().with_company(company).with_context(
            no_reset_password=True,
        )._create_user_from_template({
            "login": email,
            "email": email,
            "partner_id": self.id,
            "company_id": company.id,
            "company_ids": [(6, 0, company.ids)],
        })

    def _int_email_dealer_account(self, user):
        """A create-password link until they have signed in once, then a sign-in note."""
        if user.login_date:
            template = self.env.ref(SIGN_IN_TEMPLATE)
        else:
            user.partner_id.signup_prepare()
            template = self.env.ref(SET_PASSWORD_TEMPLATE)
        template.sudo().send_mail(user.id, force_send=True)

    def _int_dealer_account_email_notice(self, code, user, owner):
        email = user.email or user.login
        if code == "created":
            return (
                _("Account email sent"),
                _("We created a portal login and emailed %(email)s a link to create a password.", email=email),
                "success",
            )
        if code == "resent":
            return (
                _("Account email sent"),
                _("They have not signed in yet. We emailed %(email)s the create-password link again.", email=email),
                "success",
            )
        if code == "existing":
            return (
                _("They already have an account"),
                _(
                    "%(email)s already signs in. We emailed them to use that login. No new password link was sent.",
                    email=email,
                ),
                "success",
            )
        return (
            _("This email already has an account"),
            _(
                "%(email)s already belongs to %(name)s. No second account was created. "
                "Set the dealer pricelist on that contact. We emailed them %(what)s.",
                email=email,
                name=owner.display_name,
                what=_("a sign-in reminder") if user.login_date else _("the create-password link again"),
            ),
            "warning",
        )
