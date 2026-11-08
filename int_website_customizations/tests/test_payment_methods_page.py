from lxml import etree

from odoo.tests import TransactionCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


@tagged("-at_install", "post_install")
class TestPaymentMethodsPage(TransactionCase):

    def _render(self, template, values):
        website = self.env["website"].search([], limit=1) or self.env["website"].create({"name": "Pay Test"})
        qcontext = {"main_object": website, **values}
        with MockRequest(self.env, website=website) as req:
            req.is_frontend = True
            return str(self.env["ir.qweb"]._render(template, qcontext))

    def test_add_form_is_a_pop_up_only_on_the_payment_methods_page(self):
        form = etree.fromstring(self.env.ref("payment.form").get_combined_arch())
        modal = form.xpath("//div[@id='o_int_add_payment_method']")
        self.assertEqual(len(modal), 1)
        # Stock's list of methods is kept: once in the pop-up, once for checkout and elsewhere.
        self.assertEqual(len(form.xpath("//div[@id='o_payment_methods']")), 2)
        self.assertEqual(len(modal[0].xpath(".//div[@id='o_payment_methods']")), 1)
        self.assertEqual(len(modal[0].xpath(".//t[@t-call='payment.submit_button']")), 1)

        page = etree.fromstring(self.env.ref("payment.payment_methods").get_combined_arch())
        call = page.xpath("//div[contains(@class, 'o_int_paymethods')]//t[@t-call='payment.form']")
        self.assertEqual(len(call), 1)
        flags = {node.get("t-set"): node.get("t-value") for node in call[0].xpath("./t[@t-set]")}
        self.assertEqual(flags.get("int_payment_methods_page"), "True")
        self.assertEqual(flags.get("display_submit_button"), "False")

    def test_empty_page_says_nothing_is_saved(self):
        Token = self.env["payment.token"].sudo()
        rendered = self._render("payment.payment_methods", {
            "mode": "validation",
            "allow_token_selection": False,
            "allow_token_deletion": True,
            "providers_sudo": self.env["payment.provider"].sudo(),
            "payment_methods_sudo": self.env["payment.method"].sudo(),
            "tokens_sudo": Token,
            "availability_report": {},
            "reference_prefix": "V",
            "partner_id": self.env.user.partner_id.id,
            "transaction_route": "/payment/transaction",
            "landing_route": "/my/payment_method",
            "access_token": "x",
        })
        self.assertIn("You don't have any payment methods saved yet", rendered.replace("&#39;", "'"))
        self.assertNotIn("o_int_add_payment_method", rendered)
