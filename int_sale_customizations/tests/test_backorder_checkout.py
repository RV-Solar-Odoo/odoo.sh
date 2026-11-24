from types import SimpleNamespace

from lxml import etree

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


@tagged("post_install", "-at_install")
class TestBackorderCheckout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.company.account_use_credit_limit = True
        cls.warehouse = env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.website = env["website"].search([("company_id", "=", cls.company.id)], limit=1) or env["website"].create({
            "name": "Checkout Backorder Website",
            "company_id": cls.company.id,
        })
        cls.website.warehouse_id = cls.warehouse
        cls.carrier = env["delivery.carrier"].create({
            "name": "Backorder Test Pickup",
            "delivery_type": "fixed",
            "fixed_price": 0.0,
            "product_id": env.ref("delivery.product_product_delivery").id,
            "is_published": True,
            "company_id": cls.company.id,
        })
        cls.vendor = env["res.partner"].create({"name": "Checkout Backorder Vendor", "supplier_rank": 1})
        cls.net_10th = env.ref("int_account_customizations.payment_term_net_10th")
        cls.dealer = env["res.partner"].create({
            "name": "Checkout Dealer",
            "is_company": True,
            "street": "1 Main St",
            "city": "Boise",
            "zip": "83702",
            "country_id": env.ref("base.us").id,
            "email": "checkout-dealer@example.com",
        })
        cls.dealer.with_company(cls.company).write({
            "property_payment_term_id": cls.net_10th.id,
            "credit_limit": 1000.0,
        })
        cls.owner = cls._portal(cls.dealer, "checkout-owner@example.com", "owner")
        cls.buyer = cls._portal(
            env["res.partner"].create({"name": "Checkout Buyer", "parent_id": cls.dealer.id, "email": "checkout-buyer@example.com"}),
            "checkout-buyer@example.com", "buyer",
        )
        cls.viewer = cls._portal(
            env["res.partner"].create({"name": "Checkout Viewer", "parent_id": cls.dealer.id, "email": "checkout-viewer@example.com"}),
            "checkout-viewer@example.com", "viewer",
        )
        cls.manager = env["res.users"].with_context(no_reset_password=True).create({
            "name": "Checkout Sales Manager",
            "login": "checkout-manager@example.com",
            "email": "checkout-manager@example.com",
            "group_ids": [Command.set([env.ref("sales_team.group_sale_manager").id])],
        })

    @classmethod
    def _portal(cls, partner, login, role):
        partner.sudo().write({"int_portal_role": role})
        return cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name,
            "login": login,
            "email": login,
            "partner_id": partner.id,
            "company_id": cls.company.id,
            "company_ids": [Command.set([cls.company.id])],
            "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
        })

    def setUp(self):
        super().setUp()
        self.env["product.template"]._int_victron_clear_po_cache()

    def _product(self, name, on_hand=0, price=100.0):
        product = self.env["product.product"].create({
            "name": name,
            "type": "consu",
            "is_storable": True,
            "list_price": price,
            "taxes_id": [Command.clear()],
            "allow_out_of_stock_order": True,
            "website_published": True,
        })
        self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "price": price / 2,
        })
        if on_hand:
            self.env["stock.quant"]._update_available_quantity(product, self.warehouse.lot_stock_id, on_hand)
        return product

    def _cart(self, user, *lines):
        order = self.env["sale.order"].create({
            "partner_id": user.partner_id.id,
            "website_id": self.website.id,
            "warehouse_id": self.warehouse.id,
            "order_line": [
                Command.create({"product_id": product.id, "product_uom_qty": qty, "tax_ids": [Command.clear()]})
                for product, qty in lines
            ],
        })
        later = self.env.ref("int_shippo_customizations.delivery_carrier_backorder_later")
        order._set_delivery_method(later if order._int_nothing_ships_now() else self.carrier)
        return order

    def test_pay_now_leaves_out_the_backorder_and_its_shipping_and_coupons(self):
        product = self._product("Checkout Split", on_hand=2)
        cart = self._cart(self.owner, (product, 5))
        line = cart.order_line.filtered(lambda item: item.product_id == product)
        self.assertEqual(line._int_shipping_quote_qty(), 2.0)
        cart._int_backorder_split()
        back = cart.order_line.filtered("int_backorder")
        self.assertEqual(back.product_uom_qty, 3.0)
        self.assertEqual(back._int_shipping_quote_qty(), 0.0)
        self.assertEqual(line._int_shipping_quote_qty(), 2.0)
        self.assertNotIn(back, cart._int_shippo_order_lines())
        self.assertIn(back, cart._get_no_effect_on_threshold_lines())
        self.assertEqual(cart._int_amount_due_now(), cart.amount_total - 300.0)

    def test_dealer_on_terms_places_the_order_on_account(self):
        product = self._product("Checkout Terms", on_hand=10)
        cart = self._cart(self.buyer, (product, 3))
        status = cart._int_terms_for(self.buyer)
        self.assertTrue(status["eligible"])
        cart._int_place_without_payment("account", self.buyer)
        self.assertEqual(cart.state, "sale")
        self.assertTrue(cart.int_on_account)
        self.assertEqual(cart.payment_term_id, self.net_10th)
        self.assertEqual(cart._int_amount_due_now(), 0.0)

        too_big = self._cart(self.owner, (product, 7), (self._product("Checkout Big", on_hand=20, price=200.0), 5))
        status = too_big._int_terms_for(self.owner)
        self.assertFalse(status["eligible"])
        self.assertIn("available credit", status["reason"])
        with self.assertRaises(UserError):
            too_big._int_place_without_payment("account", self.owner)
        self.assertEqual(too_big.state, "draft")

        # Viewers can't order at all, and nobody else's cart can go on this account.
        self.assertFalse(self._cart(self.viewer, (product, 1))._int_terms_for(self.viewer)["on_terms"])
        stranger = self.env["res.partner"].create({"name": "Not The Dealer"})
        other_cart = self.env["sale.order"].create({
            "partner_id": stranger.id,
            "website_id": self.website.id,
            "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1})],
        })
        self.assertFalse(other_cart._int_terms_for(self.owner)["on_terms"])

    def test_backorder_does_not_use_credit(self):
        product = self._product("Checkout Credit")
        order = self._cart(self.owner, (product, 8))
        order._int_backorder_split()
        self.assertFalse(order._int_pay_now_amount())
        order._int_place_without_payment("backorder", self.owner)
        self.assertEqual(order.state, "sale")
        self.assertFalse(order.int_on_account)
        commercial = self.dealer.with_company(self.company)
        commercial.invalidate_recordset(["credit_to_invoice"])
        self.assertEqual(commercial.credit_to_invoice, 0.0)
        status = self.dealer._int_terms_status(self.company, 900.0)
        self.assertTrue(status["eligible"])
        self.assertEqual(status["available"], 1000.0)

    def test_backorder_only_needs_nothing_paid_and_a_paid_cart_is_refused(self):
        in_stock = self._product("Checkout Paid", on_hand=3)
        cart = self._cart(self.owner, (in_stock, 1))
        cart._int_backorder_split()
        with self.assertRaises(UserError):
            cart._int_place_without_payment("backorder", self.owner)
        self.assertEqual(cart.state, "draft")

    def test_customer_cancels_backordered_items_or_asks_once_the_po_is_confirmed(self):
        product = self._product("Checkout Cancel", on_hand=1)
        order = self._cart(self.owner, (product, 3))
        order._int_backorder_split()
        order.action_confirm()
        back = order.order_line.filtered("int_backorder")
        self.assertTrue(order._int_can_cancel_backorder(self.buyer))
        self.assertFalse(order._int_can_cancel_backorder(self.viewer))
        with self.assertRaises(UserError):
            order.with_user(self.viewer).int_portal_cancel_backorder(self.viewer, "delay", "")
        outcome = order.with_user(self.buyer).int_portal_cancel_backorder(self.buyer, "delay", "Found one locally")
        self.assertEqual(outcome, "cancelled")
        self.assertEqual(back.product_uom_qty, 0.0)
        self.assertEqual(order.state, "sale")
        self.assertEqual((order.order_line - back).filtered(lambda line: line.product_id == product).product_uom_qty, 1.0)

        second = self._cart(self.owner, (product, 2))
        second._int_backorder_split()
        second.action_confirm()
        second._int_backorder_purchase_orders().button_confirm()
        outcome = second.with_user(self.owner).int_portal_cancel_backorder(self.owner, "no_longer_needed", "")
        self.assertEqual(outcome, "requested")
        self.assertEqual(second.int_cancel_state, "requested")
        self.assertEqual(second.int_cancel_scope, "backorder")
        self.assertFalse(second._int_can_cancel_backorder(self.owner))
        second.int_confirm_cancellation(self.manager, False, "Vendor agreed")
        self.assertEqual(second.int_cancel_state, "approved")
        self.assertEqual(second.state, "sale")
        self.assertFalse(second.order_line.filtered(lambda line: line.int_backorder and line.product_uom_qty))

    def test_checkout_pages_have_the_new_buttons(self):
        payment = etree.fromstring(self.env.ref("website_sale.payment").get_combined_arch())
        self.assertIn("Place Order on Account", etree.tostring(payment, encoding="unicode"))
        non_free = payment.xpath("//div[@name='website_sale_non_free_cart']")[0]
        self.assertIn("_int_pay_now_amount", non_free.get("t-if"))
        self.assertEqual(non_free.getnext().get("t-else"), "")
        buttons = self.env.ref("website_sale.navigation_buttons").get_combined_arch()
        self.assertIn("Place Backorder", buttons)
        order_page = self.env.ref("sale.sale_order_portal_content").get_combined_arch()
        self.assertIn("Cancel Backordered Items", order_page)
        confirmation = self.env.ref("website_sale.confirmation").get_combined_arch()
        self.assertIn("Placed on your account", confirmation)

    def test_all_backorder_cart_ships_later_and_needs_no_parcel_quote(self):
        product = self._product("Checkout Later")
        cart = self._cart(self.owner, (product, 2))
        later = self.env.ref("int_shippo_customizations.delivery_carrier_backorder_later")
        self.assertTrue(cart._int_nothing_ships_now())
        methods = cart._get_delivery_methods()
        self.assertIn(later, methods)
        self.assertNotIn(self.carrier, methods)
        self.assertEqual(cart.carrier_id, later)
        self.assertEqual(cart.amount_delivery, 0.0)
        in_stock = self._cart(self.owner, (self._product("Checkout Now", on_hand=5), 1))
        self.assertFalse(later._is_available_for_order(in_stock))
        self.assertIn(self.carrier, in_stock._get_delivery_methods())
        cart._int_backorder_split()
        cart._int_place_without_payment("backorder", self.owner)
        self.assertEqual(cart.state, "sale")

    def test_thank_you_page_counts_the_pay_now_amount_as_paid_in_full(self):
        product = self._product("Checkout Partial", on_hand=1)
        cart = self._cart(self.owner, (product, 3))
        cart._int_backorder_split()
        self.assertTrue(cart._int_payment_matches(SimpleNamespace(amount=cart._int_pay_now_amount())))
        self.assertFalse(cart._int_payment_matches(SimpleNamespace(amount=cart.amount_total)))
        plain = self._cart(self.owner, (self._product("Checkout Whole", on_hand=5), 1))
        self.assertTrue(plain._int_payment_matches(SimpleNamespace(amount=plain.amount_total)))

        status = self.env.ref("website_sale.payment_confirmation_status").get_combined_arch()
        self.assertIn("_int_payment_matches", status)
        self.assertNotIn("order.amount_total != tx_sudo.amount", status)

    def _render_total(self, cart):
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id):
            return str(self.env["ir.ui.view"]._render_template("website_sale.total", {
                "website_sale_order": cart,
                "hide_promotions": True,
            }))

    def test_order_summary_splits_today_from_the_backorder(self):
        tax = self.env["account.tax"].create({
            "name": "Checkout Summary 10%",
            "amount": 10.0,
            "type_tax_use": "sale",
            "company_id": self.company.id,
        })
        product = self._product("Checkout Summary", on_hand=1)
        cart = self._cart(self.owner, (product, 3))
        cart.order_line.filtered(lambda line: line.product_id == product).tax_ids = tax
        cart._int_backorder_split()
        figures = cart._int_checkout_summary()
        self.assertEqual(figures["now_items"], 100.0)
        self.assertEqual(figures["now_tax"], 10.0)
        self.assertEqual(figures["due_today"], cart._int_pay_now_amount())
        self.assertEqual(figures["due_today"], 110.0)
        self.assertEqual(figures["later_qty"], 2)
        self.assertEqual(figures["later_items"], 200.0)
        self.assertEqual(figures["later_tax"], 20.0)
        html = self._render_total(cart)
        root = etree.fromstring(html, etree.HTMLParser())
        for name in ("o_order_delivery", "o_order_total_untaxed", "o_order_total_taxes", "o_order_total"):
            row = root.xpath(f"//tr[@name='{name}']")
            self.assertTrue(row and "d-none" in row[0].get("class", ""), name)
        for name in ("o_int_now_items", "o_int_now_shipping", "o_int_now_tax", "o_int_order_due_today", "o_int_order_later"):
            self.assertTrue(root.xpath(f"//tr[@name='{name}']"), name)
        self.assertIn("Paying today", html)
        self.assertIn("Billed when it ships", html)
        self.assertIn("Backordered items (2)", html)
        self.assertIn("TBD", html)
        self.assertIn("Free", html)
        self.assertIn("We'll let you know when there's an ETA and bill these items then.", html)

        cart._int_backorder_merge()
        html = self._render_total(cart)
        self.assertNotIn("Due Today", html)
        root = etree.fromstring(html, etree.HTMLParser())
        self.assertNotIn("d-none", root.xpath("//tr[@name='o_order_total']")[0].get("class", ""))

    def test_order_summary_has_no_tax_rows_for_a_tax_exempt_dealer(self):
        product = self._product("Checkout Exempt", on_hand=1)
        cart = self._cart(self.owner, (product, 2))
        cart._int_backorder_split()
        root = etree.fromstring(self._render_total(cart), etree.HTMLParser())
        self.assertFalse(root.xpath("//tr[@name='o_int_now_tax']"))
        later = root.xpath("//tr[@name='o_int_order_later']")[0]
        self.assertNotIn("Tax", "".join(later.itertext()))

    def test_order_summary_for_an_all_backorder_cart_shows_nothing_due(self):
        product = self._product("Checkout All Later")
        cart = self._cart(self.owner, (product, 2))
        cart._int_backorder_split()
        self.assertEqual(cart._int_checkout_summary()["due_today"], 0.0)
        root = etree.fromstring(self._render_total(cart), etree.HTMLParser())
        self.assertFalse(root.xpath("//tr[@name='o_int_now_items']"))
        self.assertFalse(root.xpath("//tr[@name='o_int_now_shipping']"))
        self.assertTrue(root.xpath("//tr[@name='o_int_order_due_today']"))
        self.assertTrue(root.xpath("//tr[@name='o_int_order_later']"))
