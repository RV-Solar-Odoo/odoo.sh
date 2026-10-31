from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.account_payment.tests.common import AccountPaymentCommon
from odoo.addons.sale.tests.common import SaleCommon


@tagged("-at_install", "post_install")
class TestWebsitePaidInvoice(AccountPaymentCommon, SaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].create({"name": "Invoice Test Website"})
        cls.provider.journal_id.inbound_payment_method_line_ids.filtered(
            lambda line: line.payment_provider_id == cls.provider
        ).payment_account_id = cls.inbound_payment_method_line.payment_account_id

    def test_paid_website_order_is_invoiced_and_not_emailed(self):
        self.env["ir.config_parameter"].sudo().set_param("sale.automatic_invoice", "False")
        self.sale_order.website_id = self.website
        self.amount = self.sale_order.amount_total
        tx = self._create_transaction(
            flow="redirect", sale_order_ids=[self.sale_order.id], state="done",
        )
        with mute_logger("odoo.addons.sale.models.payment_transaction"):
            tx._post_process()

        invoice = self.sale_order.invoice_ids
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.state, "posted")
        self.assertFalse(invoice.is_move_sent)
        self.assertFalse(self.env["mail.mail"].search([
            ("model", "=", "account.move"),
            ("res_id", "=", invoice.id),
        ]))

    def test_paid_backend_order_is_left_uninvoiced(self):
        self.env["ir.config_parameter"].sudo().set_param("sale.automatic_invoice", "False")
        self.sale_order.website_id = False
        self.amount = self.sale_order.amount_total
        tx = self._create_transaction(
            flow="redirect", sale_order_ids=[self.sale_order.id], state="done",
        )
        with mute_logger("odoo.addons.sale.models.payment_transaction"):
            tx._post_process()

        self.assertFalse(self.sale_order.invoice_ids)
