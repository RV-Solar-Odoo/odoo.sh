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
        cls.partner = cls.env["res.partner"].create({"name": "MAP Shop Customer"})
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
        cls.public_pl = cls.env["product.pricelist"].create({
            "name": "MAP Public",
            "website_id": cls.website.id,
        })
        cls.dealer_pl = cls.env["product.pricelist"].create({
            "name": "MAP Dealer",
            "website_id": cls.website.id,
            "item_ids": [Command.create({
                "applied_on": "3_global",
                "compute_price": "percentage",
                "percent_price": 32,
            })],
        })

    def setUp(self):
        super().setUp()
        if "map_price" not in self.env["product.template"]._fields:
            self.skipTest("MAP price is not installed")

    def _info(self, pricelist):
        with MockRequest(self.env, website=self.website, website_sale_current_pl=pricelist.id):
            return self.template._get_combination_info(product_id=self.product.id)

    def test_public_shop_uses_map_and_slashes_msrp(self):
        info = self._info(self.public_pl)
        self.assertAlmostEqual(info["price"], 850.0)
        self.assertAlmostEqual(info["list_price"], 1000.0)
        self.assertTrue(info["has_discounted_price"])
        self.assertAlmostEqual(info["int_map_price"], 850.0)
        self.assertAlmostEqual(info["int_msrp"], 1000.0)
        self.assertFalse(info["int_is_dealer"])

        with MockRequest(self.env, website=self.website, website_sale_current_pl=self.public_pl.id):
            prices = self.template._get_sales_prices(self.website)[self.template.id]
        self.assertAlmostEqual(prices["price_reduce"], 850.0)
        self.assertAlmostEqual(prices["base_price"], 1000.0)

    def test_dealer_shop_uses_the_pricelist_and_slashes_msrp(self):
        info = self._info(self.dealer_pl)
        self.assertAlmostEqual(info["price"], 680.0)
        self.assertAlmostEqual(info["list_price"], 1000.0)
        self.assertTrue(info["has_discounted_price"])
        self.assertTrue(info["int_is_dealer"])
        self.assertAlmostEqual(info["int_dealer_price"], 680.0)
        self.assertAlmostEqual(info["int_map_price"], 850.0)

        with MockRequest(self.env, website=self.website, website_sale_current_pl=self.dealer_pl.id):
            prices = self.template._get_sales_prices(self.website)[self.template.id]
        self.assertAlmostEqual(prices["price_reduce"], 680.0)
        self.assertAlmostEqual(prices["base_price"], 1000.0)

    def test_website_cart_charges_map_unless_the_order_is_a_dealer(self):
        public_order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
            "pricelist_id": self.public_pl.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        self.assertAlmostEqual(public_order.order_line.price_unit, 850.0)

        dealer_order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
            "pricelist_id": self.dealer_pl.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        self.assertAlmostEqual(dealer_order.order_line.price_unit, 680.0)

    def test_product_page_lists_msrp_map_and_dealer(self):
        info = self._info(self.dealer_pl)
        with MockRequest(self.env, website=self.website, website_sale_current_pl=self.dealer_pl.id):
            html = str(self.env["ir.ui.view"]._render_template("website_sale.product_price", {
                "combination_info": info,
                "website": self.website,
                "product": self.template,
                "editable": False,
            }))
        self.assertIn("MSRP", html)
        self.assertIn("MAP", html)
        self.assertIn("Dealer", html)
