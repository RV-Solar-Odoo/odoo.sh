from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import email_normalize


@tagged("post_install", "-at_install")
class TestDealerAccountEmail(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Dealer Account Test Co"})
        cls.env.user.write({"company_ids": [(4, cls.company.id)]})

    def _partner(self, name, email):
        return self.env["res.partner"].create({
            "name": name,
            "email": email,
            "company_id": self.company.id,
        })

    def _users(self, email):
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        return Users.search(Users._get_login_domain(email_normalize(email)))

    def _mark_signed_in(self, user):
        self.env.cr.execute(
            """
            INSERT INTO res_users_log (create_uid, create_date, write_uid, write_date)
            VALUES (%s, NOW() AT TIME ZONE 'UTC', %s, NOW() AT TIME ZONE 'UTC')
            """,
            (user.id, user.id),
        )
        user.invalidate_recordset(["login_date", "log_ids"])

    def test_new_dealer_gets_a_create_password_email(self):
        partner = self._partner("New Dealer", "new-dealer@example.com")
        code, user, owner = partner._int_send_dealer_account_email()
        self.assertEqual(code, "created")
        self.assertEqual(owner, partner)
        self.assertEqual(self._users(partner.email), user)
        self.assertTrue(user._is_portal())
        self.assertFalse(user.login_date)
        self.assertEqual(user.partner_id.signup_type, "signup")

    def test_unopened_invite_is_sent_again(self):
        partner = self._partner("Waiting Dealer", "waiting-dealer@example.com")
        partner._int_send_dealer_account_email()
        code, user, owner = partner._int_send_dealer_account_email()
        self.assertEqual(code, "resent")
        self.assertEqual(owner, partner)
        self.assertEqual(len(self._users(partner.email)), 1)
        self.assertEqual(user.partner_id.signup_type, "signup")

    def test_checkout_account_gets_a_sign_in_email(self):
        partner = self._partner("Checkout Dealer", "checkout-dealer@example.com")
        _code, user, _owner = partner._int_send_dealer_account_email()
        self._mark_signed_in(user)
        code, again, owner = partner._int_send_dealer_account_email()
        self.assertEqual(code, "existing")
        self.assertEqual(again, user)
        self.assertEqual(owner, partner)
        self.assertEqual(len(self._users(partner.email)), 1)
        mail = self.env["mail.mail"].search([
            ("email_to", "ilike", "checkout-dealer@example.com"),
        ], order="id desc", limit=1)
        self.assertIn("dealer account is ready", (mail.subject or "").lower())

    def test_same_email_on_another_contact_does_not_create_a_second_login(self):
        owner = self._partner("Checkout Contact", "shared-dealer@example.com")
        _code, user, _owner = owner._int_send_dealer_account_email()
        self._mark_signed_in(user)
        application = self._partner("Application Contact", "shared-dealer@example.com")
        code, again, account_owner = application._int_send_dealer_account_email()
        self.assertEqual(code, "other_contact")
        self.assertEqual(again, user)
        self.assertEqual(account_owner, owner)
        self.assertFalse(application.user_ids)
        self.assertEqual(len(self._users(application.email)), 1)

    def test_internal_email_is_refused(self):
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Inside Sales",
            "login": "inside-sales@example.com",
            "email": "inside-sales@example.com",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        partner = self._partner("Staff Twin", "inside-sales@example.com")
        with self.assertRaises(UserError):
            partner._int_send_dealer_account_email()
