from lxml import html

from odoo.tests import TransactionCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


@tagged("-at_install", "post_install")
class TestShopSearch(TransactionCase):

    def _render_form(self, **values):
        website = self.env["website"].search([], limit=1)
        with MockRequest(self.env, website=website):
            rendered = self.env["ir.qweb"]._render("website.website_search_box_input", values)
        return html.fromstring(str(rendered)).xpath("//form")[0]

    def test_product_search_ignores_the_current_category(self):
        form = self._render_form(
            search_type="products",
            action="/shop/category/distribution-wiring-84?tags=1",
            placeholder="Search in Distribution & Wiring",
        )
        self.assertEqual(form.get("action"), "/shop")
        self.assertEqual(form.xpath(".//input[@name='search']")[0].get("placeholder"), "Search products")

    def test_other_search_boxes_keep_their_own_action(self):
        form = self._render_form(search_type="pages", action="/pages", placeholder="Find a page")
        self.assertEqual(form.get("action"), "/pages")
        self.assertEqual(form.xpath(".//input[@name='search']")[0].get("placeholder"), "Find a page")
