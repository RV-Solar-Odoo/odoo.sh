from lxml import html

from odoo.tests import HttpCase, TransactionCase, tagged

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


@tagged("-at_install", "post_install")
class TestShopSearchCategories(HttpCase):

    def test_search_keeps_categories_without_a_match(self):
        Category = self.env["product.public.category"]
        Template = self.env["product.template"]
        matching = Category.create({"name": "Qzx Matching Category"})
        other = Category.create({"name": "Qzx Other Category"})
        Template.create({
            "name": "Qzxfindme Product",
            "is_published": True,
            "sale_ok": True,
            "public_categ_ids": [(4, matching.id)],
        })
        Template.create({
            "name": "Qzxhidden Product",
            "is_published": True,
            "sale_ok": True,
            "public_categ_ids": [(4, other.id)],
        })

        page = self.url_open("/shop?search=Qzxfindme").text
        self.assertIn("Qzxfindme Product", page)
        self.assertNotIn("Qzxhidden Product", page)
        self.assertIn("Qzx Matching Category", page)
        self.assertIn("Qzx Other Category", page)
