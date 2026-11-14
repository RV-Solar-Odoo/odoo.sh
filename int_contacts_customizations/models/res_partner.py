from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import email_normalize

SIGN_IN_TEMPLATE = "int_contacts_customizations.mail_template_dealer_sign_in"
SET_PASSWORD_TEMPLATE = "auth_signup.portal_set_password_email"


class ResPartner(models.Model):
    _inherit = "res.partner"

    int_portal_role = fields.Selection(
        [
            ("owner", "Owner"),
            ("buyer", "Buyer"),
            ("accountant", "Accountant"),
            ("viewer", "Viewer"),
        ],
        string="Portal role",
        default="owner",
        help="What this contact can do in My Portal. Set it from My Portal → Users, or here. "
             "Owner can do everything. Buyer can order but not see invoices, payments, or credit. "
             "Accountant can see the money but not order. Viewer can see orders and tracking.",
    )
    int_address_category = fields.Selection(
        [
            ("business", "Business location"),
            ("customer", "Customer / drop-ship"),
        ],
        string="Address category",
        default="business",
        help="Business locations belong to the dealer. Customer addresses are drop-ship sites.",
    )
    int_location_type = fields.Selection(
        [
            ("commercial", "Commercial"),
            ("residential", "Residential"),
        ],
        string="Location type",
    )
    int_has_loading_dock = fields.Boolean(string="Loading dock")
    int_has_forklift = fields.Boolean(string="Forklift on site")

    @api.model
    def _get_frontend_writable_fields(self):
        return super()._get_frontend_writable_fields() | {
            "int_address_category",
            "int_location_type",
            "int_has_loading_dock",
            "int_has_forklift",
        }

    def _can_be_edited_by_current_customer(self, *args, **kwargs):
        if self.env.user.share and not self.env.user.int_portal_can("manage_addresses"):
            return False
        return super()._can_be_edited_by_current_customer(*args, **kwargs)

    def write(self, vals):
        if "int_portal_role" in vals and not self.env.su and not self.env.user.has_group("base.group_user"):
            raise AccessError(_("Only staff or the account owner can change a portal role."))
        vals = dict(vals)
        if vals.get("int_location_type") == "residential":
            vals["int_has_loading_dock"] = False
            vals["int_has_forklift"] = False
        if vals.get("int_address_category") == "customer":
            companies = self.filtered(lambda partner: partner.is_company and not partner.parent_id)
            if companies:
                raise UserError(_("The company address stays a business location."))
        return super().write(vals)

    def _int_portal_family_partners(self):
        """This company contact and every contact underneath it."""
        self.ensure_one()
        commercial = self.commercial_partner_id
        return self.env["res.partner"].sudo().search([("id", "child_of", commercial.id)])

    def _int_portal_family_users(self):
        """Portal logins on this company contact and its child contacts."""
        self.ensure_one()
        return self.env["res.users"].sudo().with_context(active_test=False).search([
            ("partner_id", "in", self._int_portal_family_partners().ids),
            ("share", "=", True),
        ])

    def _int_portal_owner_count(self):
        users = self._int_portal_family_users().filtered("active")
        return len(users.filtered(lambda user: (user.partner_id.int_portal_role or "owner") == "owner"))

    def int_portal_invite_user(self, name, email, role):
        """Create a child contact and portal login, or reuse one already in this company."""
        self.ensure_one()
        commercial = self.commercial_partner_id
        email = email_normalize(email or "")
        if not email or not (name or "").strip():
            raise UserError(_("Enter a name and an email."))
        if role not in dict(self._fields["int_portal_role"].selection):
            raise UserError(_("Choose a role."))
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        user = Users.search(Users._get_login_domain(email), limit=1)
        if not user:
            user = Users.search(Users._get_email_domain(email), limit=1)
        if user and user._is_internal():
            raise UserError(_("This email belongs to an internal user. No portal account was created."))
        family = commercial._int_portal_family_partners()
        if user and user.partner_id not in family:
            raise UserError(_("This email is linked to another account. Contact us."))
        if user:
            user.partner_id.sudo().write({"int_portal_role": role})
            if not user.active:
                user.active = True
            user.partner_id._int_send_dealer_account_email()
            user.int_session_epoch = (user.int_session_epoch or 0) + 1
            return user
        child = self.env["res.partner"].sudo().create({
            "name": name.strip(),
            "email": email,
            "parent_id": commercial.id,
            "type": "contact",
            "int_portal_role": role,
            "company_id": commercial.company_id.id or self.env.company.id,
        })
        child._int_send_dealer_account_email()
        return child.user_ids[:1]

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

        family = self.commercial_partner_id._int_portal_family_partners()
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
