from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import email_normalize


@tagged("post_install", "-at_install")
class TestDealerApplicationAccount(TransactionCase):

    def _pricelist(self, name, company):
        return self.env["product.pricelist"].create({
            "name": name,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
        })

    def _invite(self, lead, pricelist, company, **extra):
        action = lead.action_int_open_dealer_invite()
        wizard = self.env["int.dealer.invite"].with_context(**action["context"]).create({
            "pricelist_id": pricelist.id,
            **extra,
        })
        self.assertEqual(wizard.lead_id, lead)
        self.assertEqual(wizard.company_id, company)
        return wizard.action_confirm()

    def test_invite_sets_pricelist_tag_and_one_login(self):
        company = self.env.company
        pricelist = self._pricelist("Invite Dealer", company)
        lead = self.env["crm.lead"].create({
            "name": "New dealer",
            "contact_name": "Pat Dealer",
            "email_from": "invite-dealer@example.com",
            "type": "opportunity",
            "company_id": company.id,
        })
        self._invite(lead, pricelist, company)
        partner = lead.partner_id
        self.assertEqual(
            partner.with_company(company).specific_property_product_pricelist,
            pricelist,
        )
        self.assertEqual(
            partner.category_id.filtered(lambda category: category.name == "RVSB Dealer"),
            partner._int_rvsb_dealer_category(),
        )
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        users = Users.search(Users._get_login_domain(email_normalize(partner.email)))
        self.assertEqual(len(users), 1)
        self.assertFalse(users.login_date)

        self._invite(lead, pricelist, company)
        users = Users.search(Users._get_login_domain(email_normalize(partner.email)))
        self.assertEqual(len(users), 1)
        self.assertEqual(
            len(partner.category_id.filtered(lambda category: category.name == "RVSB Dealer")),
            1,
        )

    def _lead(self, email, company):
        return self.env["crm.lead"].create({
            "name": "Credit dealer",
            "contact_name": "Credit Dealer",
            "partner_name": "Credit Dealer Co",
            "email_from": email,
            "type": "opportunity",
            "company_id": company.id,
        })

    def test_invite_sets_a_chosen_credit_limit_on_the_company_contact(self):
        company = self.env.company
        pricelist = self._pricelist("Credit Invite", company)
        lead = self._lead("credit-invite@example.com", company)
        self._invite(lead, pricelist, company, credit_limit_choice="3000")
        commercial = lead.partner_id.commercial_partner_id.sudo().with_company(company)
        self.assertEqual(commercial.credit_limit, 3000)
        self.assertTrue(commercial.use_partner_credit_limit)

        self._invite(lead, pricelist, company, credit_limit_choice="other", credit_limit_other=2500)
        self.assertEqual(commercial.credit_limit, 2500)

        # No limit leaves what is already there.
        self._invite(lead, pricelist, company)
        self.assertEqual(commercial.credit_limit, 2500)

    def test_other_credit_limit_needs_an_amount(self):
        company = self.env.company
        lead = self._lead("credit-other@example.com", company)
        action = lead.action_int_open_dealer_invite()
        with self.assertRaises(ValidationError):
            self.env["int.dealer.invite"].with_context(**action["context"]).create({
                "pricelist_id": self._pricelist("Credit Other", company).id,
                "credit_limit_choice": "other",
                "credit_limit_other": 0,
            })

    def test_invite_reuses_checkout_login_and_sets_its_pricelist(self):
        company = self.env.company
        pricelist = self._pricelist("Applied Later Dealer", company)
        partner = self.env["res.partner"].create({
            "name": "Checkout Customer",
            "email": "applied-later-invite@example.com",
            "company_id": company.id,
        })
        partner._int_send_dealer_account_email()
        lead = self.env["crm.lead"].create({
            "name": "Applied later",
            "email_from": "applied-later-invite@example.com",
            "type": "opportunity",
            "company_id": company.id,
        })
        self._invite(lead, pricelist, company)
        self.assertEqual(lead.partner_id, partner)
        self.assertEqual(
            partner.with_company(company).specific_property_product_pricelist,
            pricelist,
        )
        self.assertIn("RVSB Dealer", partner.category_id.mapped("name"))
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        users = Users.search(Users._get_login_domain(email_normalize(partner.email)))
        self.assertEqual(len(users), 1)
        self.assertEqual(users.partner_id, partner)

    def test_invite_requires_an_email(self):
        lead = self.env["crm.lead"].create({
            "name": "No email",
            "type": "opportunity",
        })
        with self.assertRaises(UserError):
            lead.action_int_open_dealer_invite()

    def test_application_reuses_the_checkout_login(self):
        partner = self.env["res.partner"].create({
            "name": "Checkout Customer",
            "email": "applied-later@example.com",
        })
        partner._int_send_dealer_account_email()
        lead = self.env["crm.lead"].create({
            "name": "Applied later",
            "email_from": "applied-later@example.com",
            "type": "opportunity",
        })
        lead.action_int_send_dealer_account_email()
        self.assertEqual(lead.partner_id, partner)
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        users = Users.search(Users._get_login_domain(email_normalize(partner.email)))
        self.assertEqual(users.partner_id, partner)
        self.assertEqual(len(users), 1)
