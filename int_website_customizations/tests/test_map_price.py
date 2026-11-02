from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


@tagged("-at_install", "post_install")
class TestMapWebsitePrice(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "map_price" not in cls.env["product.template"]._fields:
            return
        cls.website = cls.env["website"].search([], limit=1)
        if not cls.website:
            cls.website = cls.env["website"].create({"name": "MAP Test Website"})
        public_partner = cls.env.ref("base.public_user").partner_id
        cls.public_pl = public_partner.property_product_pricelist
        if not cls.public_pl:
            cls.public_pl = cls.env["product.pricelist"].search([], limit=1)
            public_partner.property_product_pricelist = cls.public_pl.id
        cls.dealer_pl = cls.env["product.pricelist"].create({
            "name": "MAP Dealer",
            "website_id": cls.website.id,
            "item_ids": [Command.create({
                "applied_on": "3_global",
                "compute_price": "percentage",
                "percent_price": 32,
            })],
        })
        cls.retail_partner = cls.env["res.partner"].create({
            "name": "MAP Retail Customer",
            "property_product_pricelist": cls.public_pl.id,
        })
        cls.dealer_partner = cls.env["res.partner"].create({
            "name": "MAP Dealer Customer",
            "property_product_pricelist": cls.dealer_pl.id,
        })
        cls.template = cls.env["product.template"].create({
            "name": "MAP Test Inverter",
            "type": "consu",
            "list_price": 1000.0,
            "map_price": 850.0,
            "sale_ok": True,
            "website_published": True,
            "taxes_id": [Command.clear()],
        })
        cls.product = cls.template.product_variant_id

    def setUp(self):
        super().setUp()
        if "map_price" not in self.env["product.template"]._fields:
            self.skipTest("MAP price is not installed")

    def _info(self, partner, session_pricelist=None):
        tmpl = self.template.with_context(int_pricing_partner_id=partner.id)
        pl = session_pricelist or partner.property_product_pricelist
        with MockRequest(self.env, website=self.website, website_sale_current_pl=pl.id):
            return tmpl._get_combination_info(product_id=self.product.id)

    def test_public_shop_uses_map_and_slashes_msrp(self):
        info = self._info(self.retail_partner)
        self.assertAlmostEqual(info["price"], 850.0)
        self.assertAlmostEqual(info["list_price"], 1000.0)
        self.assertTrue(info["has_discounted_price"])
        self.assertFalse(info["int_is_dealer"])

        tmpl = self.template.with_context(int_pricing_partner_id=self.retail_partner.id)
        with MockRequest(self.env, website=self.website, website_sale_current_pl=self.public_pl.id):
            prices = tmpl._get_sales_prices(self.website)[self.template.id]
        self.assertAlmostEqual(prices["price_reduce"], 850.0)
        self.assertAlmostEqual(prices["base_price"], 1000.0)

    def test_dealer_shop_uses_the_contact_pricelist(self):
        info = self._info(self.dealer_partner)
        self.assertAlmostEqual(info["price"], 680.0)
        self.assertAlmostEqual(info["list_price"], 1000.0)
        self.assertTrue(info["has_discounted_price"])
        self.assertTrue(info["int_is_dealer"])
        self.assertAlmostEqual(info["int_dealer_price"], 680.0)
        self.assertAlmostEqual(info["int_map_price"], 850.0)
        self.assertAlmostEqual(info["int_msrp"], 1000.0)

        tmpl = self.template.with_context(int_pricing_partner_id=self.dealer_partner.id)
        with MockRequest(self.env, website=self.website, website_sale_current_pl=self.dealer_pl.id):
            prices = tmpl._get_sales_prices(self.website)[self.template.id]
        self.assertAlmostEqual(prices["price_reduce"], 680.0)
        self.assertAlmostEqual(prices["base_price"], 1000.0)

    def test_session_pricelist_does_not_make_a_retail_contact_a_dealer(self):
        info = self._info(self.retail_partner, session_pricelist=self.dealer_pl)
        self.assertFalse(info["int_is_dealer"])
        self.assertAlmostEqual(info["price"], 850.0)

    def test_website_cart_follows_the_contact_pricelist(self):
        public_order = self.env["sale.order"].create({
            "partner_id": self.retail_partner.id,
            "website_id": self.website.id,
            "pricelist_id": self.dealer_pl.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        self.assertAlmostEqual(public_order.order_line.price_unit, 850.0)

        dealer_order = self.env["sale.order"].create({
            "partner_id": self.dealer_partner.id,
            "website_id": self.website.id,
            "pricelist_id": self.public_pl.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        self.assertAlmostEqual(dealer_order.order_line.price_unit, 680.0)

    def _render_price(self, info):
        return str(self.env["ir.ui.view"]._render_template("website_sale.product_price", {
            "combination_info": info,
            "website": self.website,
            "product": self.template,
            "editable": False,
        }))

    def test_public_product_page_keeps_only_the_two_prices(self):
        html = self._render_price(self._info(self.retail_partner))
        self.assertNotIn("MSRP", html)
        self.assertNotIn("MAP", html)
        self.assertNotIn("Dealer", html)
        self.assertLess(html.find("product_list_price"), html.find("oe_price"))
        self.assertNotIn("oe_default_price mb-0 h6", html)

    def test_dealer_product_page_lists_msrp_map_and_dealer(self):
        html = self._render_price(self._info(self.dealer_partner))
        self.assertIn("MSRP", html)
        self.assertIn("MAP", html)
        self.assertIn("Dealer", html)
        self.assertIn("o_int_price_breakdown", html)
