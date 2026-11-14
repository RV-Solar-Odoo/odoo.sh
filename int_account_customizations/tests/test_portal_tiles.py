from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalTiles(TransactionCase):

    def _tile_condition(self, arch, url):
        nodes = arch.xpath(
            "//t[@t-call='portal.portal_docs_entry'][t[@t-set='url' and @t-value=\"%s\"]]" % url
        )
        self.assertEqual(len(nodes), 1, url)
        return nodes[0].get("t-if") or ""

    def test_financial_tiles_are_the_ones_gated(self):
        arch = etree.fromstring(self.env.ref("portal.portal_my_home").get_combined_arch().encode())
        orders = self._tile_condition(arch, "'/my/orders'")
        invoices = self._tile_condition(arch, "'/my/invoices?filterby=invoices'")
        bills = self._tile_condition(arch, "'/my/invoices?filterby=bills'")
        overdue = self._tile_condition(arch, "'/my/invoices?filterby=overdue_invoices'")
        payments = self._tile_condition(arch, "'/my/payment_method'")
        self.assertNotIn("view_invoices", orders)
        self.assertIn("view_invoices", invoices)
        self.assertIn("view_invoices", bills)
        self.assertIn("view_invoices", overdue)
        self.assertIn("make_payments", payments)
        self.assertIn("existing_tokens", payments)
