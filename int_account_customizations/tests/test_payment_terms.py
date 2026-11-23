from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDealerTerms(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.account_use_credit_limit = True
        cls.net_10th = cls.env.ref("int_account_customizations.payment_term_net_10th")
        cls.immediate = cls.env.ref("account.account_payment_term_immediate")
        cls.dealer = cls.env["res.partner"].create({"name": "Terms Dealer", "is_company": True})
        cls.buyer = cls.env["res.partner"].create({"name": "Terms Buyer", "parent_id": cls.dealer.id})

    def _set(self, **values):
        self.dealer.with_company(self.company).write(values)

    def test_net_10th_is_due_on_the_10th_of_next_month(self):
        line = self.net_10th.line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line._get_due_date(fields.Date.to_date("2026-11-21")), fields.Date.to_date("2026-12-10"))
        self.assertEqual(line._get_due_date(fields.Date.to_date("2026-11-01")), fields.Date.to_date("2026-12-10"))

    def test_terms_need_a_limit_no_overdue_invoice_and_room(self):
        status = self.buyer._int_terms_status(self.company, 100.0)
        self.assertFalse(status["on_terms"])
        self.assertFalse(status["reason"])

        self._set(property_payment_term_id=self.immediate.id)
        self.assertFalse(self.buyer._int_terms_status(self.company, 100.0)["on_terms"])

        self._set(property_payment_term_id=self.net_10th.id)
        status = self.buyer._int_terms_status(self.company, 100.0)
        self.assertTrue(status["on_terms"])
        self.assertFalse(status["eligible"])
        self.assertIn("credit limit", status["reason"])

        self._set(credit_limit=1000.0)
        status = self.buyer._int_terms_status(self.company, 100.0)
        self.assertTrue(status["eligible"])
        self.assertEqual(status["term"], self.net_10th)
        self.assertEqual(status["available"], 1000.0)

        over = self.buyer._int_terms_status(self.company, 1500.0)
        self.assertFalse(over["eligible"])
        self.assertNotIn("1,000", over["reason"])
        shown = self.buyer._int_terms_status(self.company, 1500.0, show_figures=True)
        self.assertIn("1,000", shown["reason"])

        # An old invoice that is still open blocks terms and uses credit.
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.dealer.id,
            "invoice_date": fields.Date.today() - timedelta(days=60),
            "invoice_line_ids": [Command.create({
                "name": "Old order",
                "quantity": 1,
                "price_unit": 50.0,
                "tax_ids": [Command.clear()],
            })],
        })
        invoice.action_post()
        self.assertLess(invoice.invoice_date_due, fields.Date.today())
        self.dealer.invalidate_recordset(["credit"])
        status = self.buyer._int_terms_status(self.company, 100.0)
        self.assertFalse(status["eligible"])
        self.assertIn("overdue", status["reason"])

        invoice.button_draft()
        invoice.invoice_date = fields.Date.today()
        invoice.action_post()
        self.assertGreater(invoice.invoice_date_due, fields.Date.today())
        self.dealer.invalidate_recordset(["credit"])
        status = self.buyer._int_terms_status(self.company, 100.0)
        self.assertTrue(status["eligible"])
        self.assertEqual(status["available"], 950.0)

    def test_contact_warns_when_a_credit_limit_has_no_customer_terms(self):
        dealer = self.dealer.with_company(self.company)
        self._set(credit_limit=2000.0)
        dealer.invalidate_recordset(["int_terms_warning"])
        self.assertIn("no customer payment terms", dealer.int_terms_warning)

        # Terms under Purchase don't count, and the warning says so.
        self._set(property_supplier_payment_term_id=self.net_10th.id)
        dealer.invalidate_recordset(["int_terms_warning"])
        self.assertIn("under Purchase", dealer.int_terms_warning)

        self._set(property_payment_term_id=self.net_10th.id)
        dealer.invalidate_recordset(["int_terms_warning"])
        self.assertFalse(dealer.int_terms_warning)
        self.assertFalse(self.buyer.with_company(self.company).int_terms_warning)
