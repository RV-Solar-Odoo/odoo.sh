from odoo.tests import TransactionCase, tagged
from odoo.tools import email_normalize


@tagged("post_install", "-at_install")
class TestDealerApplicationAccount(TransactionCase):

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
