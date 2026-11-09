from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalCredit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

    def _partner(self, name, **extra):
        values = {"name": name, "company_id": self.company.id}
        values.update(extra)
        return self.env["res.partner"].create(values)

    def _portal_user(self, partner, login, role):
        partner.sudo().int_portal_role = role
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name,
            "login": login,
            "email": login,
            "partner_id": partner.id,
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
        })

    def _limit(self, partner, amount):
        partner.with_company(self.company).sudo().credit_limit = amount

    def test_credit_figures_match_the_stated_rules(self):
        Users = self.env["res.users"]
        under = Users._int_portal_credit_figures(50, 0, 100, self.currency)
        self.assertEqual(under["level"], "ok")
        self.assertEqual(under["available"], 50)
        near = Users._int_portal_credit_figures(80, 0, 100, self.currency)
        self.assertEqual(near["level"], "warn")
        over = Users._int_portal_credit_figures(80, 30, 100, self.currency)
        self.assertEqual(over["used"], 110)
        self.assertEqual(over["available"], 0)
        self.assertEqual(over["over"], 10)
        self.assertEqual(over["level"], "over")
        self.assertEqual(over["percent"], 100)
        balance = Users._int_portal_credit_figures(-30, 10, 100, self.currency)
        self.assertEqual(balance["credit_on_account"], 30)
        self.assertEqual(balance["used"], 10)
        self.assertEqual(balance["available"], 90)

    def test_credit_card_follows_the_role_and_the_company_switch(self):
        self.company.account_use_credit_limit = True
        dealer = self._partner("Credit Dealer Co", is_company=True)
        self._limit(dealer, 1000)
        owner = self._portal_user(dealer, "owner-credit-portal@example.com", "owner")
        self.assertTrue(owner._int_portal_credit())
        accountant = self._partner("Credit Accountant", parent_id=dealer.id, email="acct-credit-portal@example.com")
        accountant_user = self._portal_user(accountant, "acct-credit-portal@example.com", "accountant")
        self.assertTrue(accountant_user._int_portal_credit())
        buyer = self._partner("Credit Buyer", parent_id=dealer.id, email="buyer-credit-portal@example.com")
        buyer_user = self._portal_user(buyer, "buyer-credit-portal@example.com", "buyer")
        self.assertFalse(buyer_user._int_portal_credit())
        viewer = self._partner("Credit Viewer", parent_id=dealer.id, email="viewer-credit-portal@example.com")
        viewer_user = self._portal_user(viewer, "viewer-credit-portal@example.com", "viewer")
        self.assertFalse(viewer_user._int_portal_credit())
        self._limit(dealer, 0)
        self.assertFalse(owner._int_portal_credit())
        self._limit(dealer, 1000)
        self.company.account_use_credit_limit = False
        self.assertFalse(owner._int_portal_credit())

    def test_internal_user_can_see_credit_whatever_the_role(self):
        self.company.account_use_credit_limit = True
        partner = self._partner("Staff Credit")
        self._limit(partner, 500)
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Staff Credit",
            "login": "staff-credit-portal@example.com",
            "email": "staff-credit-portal@example.com",
            "partner_id": partner.id,
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_user").id])],
        })
        partner.sudo().int_portal_role = "buyer"
        self.assertTrue(user._int_portal_credit())

    def test_credit_matches_an_open_invoice_and_an_uninvoiced_order(self):
        self.company.account_use_credit_limit = True
        partner = self._partner("Invoiced Dealer", is_company=True)
        self._limit(partner, 1000)
        user = self._portal_user(partner, "invoiced-dealer-portal@example.com", "owner")
        income = self.env["account.account"].search([
            ("account_type", "=", "income"),
            ("company_ids", "in", self.company.id),
        ], limit=1)
        if not income:
            income = self.env["account.account"].search([
                ("account_type", "=", "income"),
            ], limit=1)
        self.assertTrue(income)
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [Command.create({
                "name": "Open invoice",
                "quantity": 1,
                "price_unit": 40,
                "account_id": income.id,
                "tax_ids": [Command.clear()],
            })],
        })
        invoice.action_post()
        product = self.env["product.product"].create({
            "name": "Uninvoiced portal service",
            "type": "service",
            "list_price": 25,
            "invoice_policy": "order",
            "taxes_id": [Command.clear()],
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": 1,
                "price_unit": 25,
            })],
        })
        order.action_confirm()
        info = user._int_portal_credit()
        commercial = partner.with_company(self.company).sudo()
        self.assertGreater(commercial.credit, 0)
        self.assertGreater(commercial.credit_to_invoice, 0)
        self.assertAlmostEqual(info["used"], commercial.credit + commercial.credit_to_invoice, places=2)
        self.assertAlmostEqual(info["limit"], commercial.credit_limit, places=2)
