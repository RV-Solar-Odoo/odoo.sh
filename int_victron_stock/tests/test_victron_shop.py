from odoo import fields
from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


@tagged("post_install", "-at_install")
class TestVictronShop(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.warehouse = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.website = env["website"].search([], limit=1)
        if not cls.website:
            cls.website = env["website"].create({
                "name": "Victron Test Website",
                "company_id": env.company.id,
            })
        cls.website.warehouse_id = cls.warehouse
        cls.partner = env["res.partner"].create({"name": "Victron Shop Customer"})
        cls.vendor = env["res.partner"].create({
            "name": "Victron Energy Test Vendor",
            "supplier_rank": 1,
        })
        cls.casey = env["res.users"].with_context(no_reset_password=True).create({
            "name": "Casey Shirts",
            "login": "casey.shirts.victron.test",
            "email": "casey.shirts.victron.test@example.com",
        })
        icp = env["ir.config_parameter"].sudo()
        icp.set_param("int_victron.vendor_partner_id", str(cls.vendor.id))
        icp.set_param("int_victron.buyer_user_id", str(cls.casey.id))
        icp.set_param("int_victron.lead_time_label", "within 7–10 days")

    def _product(self, name, on_hand, victron):
        product = self.env["product.product"].create({
            "name": name,
            "type": "consu",
            "is_storable": True,
            "list_price": 100.0,
            "allow_out_of_stock_order": False,
        })
        product.product_tmpl_id.victron_qty = victron
        if on_hand:
            self.env["stock.quant"]._update_available_quantity(
                product, self.warehouse.lot_stock_id, on_hand
            )
        return product

    def _order(self, product, qty):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
            "warehouse_id": self.warehouse.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": qty,
            })],
        })

    def test_victron_feed_is_not_our_stock(self):
        product = self._product("Feed Only", on_hand=0, victron=0)
        product.default_code = "FEEDONLY1"
        self.env["int.victron.feed"]._replace_from_rows([
            {
                "sku": "FEEDONLY1",
                "description": "Feed Only",
                "stock_quantity": 12,
                "additional_stock_quantity": 4,
            },
            {
                "sku": "NOTOURS",
                "description": "Not in our catalog",
                "stock_quantity": 3,
            },
        ], "sku", "stock_quantity")

        ours = self.env["int.victron.feed"].search([("sku", "=", "FEEDONLY1")])
        self.assertEqual(ours.qty, 12)
        self.assertEqual(ours.additional_qty, 4)
        self.assertEqual(ours.product_id, product.product_tmpl_id)
        other = self.env["int.victron.feed"].search([("sku", "=", "NOTOURS")])
        self.assertFalse(other.product_id)
        self.assertEqual(product.qty_available, 0)
        self.assertFalse(self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("quantity", ">", 0),
        ]))

        self.env["int.victron.feed"]._replace_from_rows([], "sku", "stock_quantity")
        self.assertFalse(self.env["int.victron.feed"].search([("sku", "=", "FEEDONLY1")]))

    def test_labels_show_full_warehouse_stock_and_cap_victron(self):
        product = self._product("Blue Solar", on_hand=17, victron=45)
        lines = product.product_tmpl_id._int_availability_lines(product)
        labels = [line["label"] for line in lines]
        details = {line["status"]: line["detail"] for line in lines}
        self.assertIn("17 in stock — ready to ship", labels)
        self.assertEqual(details["immediate"], "17 in stock")
        self.assertTrue(details["backup"].startswith("20+ more available"))
        self.assertFalse(any("45" in label for label in labels))
        self.assertNotIn("45", details["backup"])

        plenty = self._product("Big Pile", on_hand=143, victron=8)
        plenty_labels = [
            line["label"] for line in plenty.product_tmpl_id._int_availability_lines(plenty)
        ]
        self.assertIn("143 in stock — ready to ship", plenty_labels)
        self.assertTrue(any(label.startswith("8 more available") for label in plenty_labels))
        self.assertFalse(any("20+" in label for label in plenty_labels))

    def test_shop_payload_hides_victron_quantity(self):
        product = self._product("Blue Solar", on_hand=17, victron=45)
        template = product.product_tmpl_id
        public = self.env.ref("base.public_user")
        with self.assertRaises(AccessError):
            template.with_user(public).read(["victron_qty"])

        with MockRequest(self.env, website=self.website):
            info = template.with_context(
                website_sale_stock_get_quantity=True
            )._get_additionnal_combination_info(
                product, 1.0, product.uom_id, fields.Datetime.now(), self.website
            )
        self.assertEqual(info["free_qty"], 17)
        self.assertTrue(info["allow_out_of_stock_order"])
        self.assertFalse(info["show_availability"])
        self.assertNotIn("victron_qty", info)
        rendered = " ".join(line["label"] for line in info["int_availability_lines"])
        self.assertIn("17 in stock — ready to ship", rendered)
        self.assertIn("20+", rendered)
        self.assertNotIn("45", rendered)

    def test_cart_accepts_victron_stock_and_blocks_past_it_without_a_number(self):
        product = self._product("Blue Solar", on_hand=17, victron=45)
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
            "warehouse_id": self.warehouse.id,
        })
        qty, warning = order._verify_updated_quantity(
            self.env["sale.order.line"], product.id, 40, product.uom_id.id
        )
        self.assertEqual(qty, 40)
        self.assertFalse(warning)

        qty, warning = order._verify_updated_quantity(
            self.env["sale.order.line"], product.id, 80, product.uom_id.id
        )
        self.assertEqual(qty, 80)
        self.assertIn("80", warning)
        self.assertIn("Contact us for a quote on larger quantities.", warning)
        self.assertNotIn("62", warning)
        self.assertNotIn("45", warning)

        sale = self._order(product, 80)
        self.assertFalse(sale.order_line._check_availability())
        self.assertIn("Contact us for a quote on larger quantities.", sale.order_line.shop_warning)
        self.assertNotIn("45", sale.order_line.shop_warning)

        allowed = self._order(product, 40)
        self.assertTrue(allowed.order_line._check_availability())
        self.assertEqual(
            allowed.order_line._int_victron_cart_note(),
            "17 ship now · 23 ship within 7–10 days",
        )

    def test_confirm_drafts_one_rfq_for_casey_and_reopens_the_activity(self):
        product = self._product("MultiPlus", on_hand=10, victron=50)
        order = self._order(product, 40)
        order.action_confirm()

        po = self.env["purchase.order"].search([
            ("int_victron_rfq", "=", True),
            ("partner_id", "=", self.vendor.id),
            ("state", "=", "draft"),
        ])
        self.assertEqual(len(po), 1)
        self.assertEqual(po.user_id, self.casey)
        self.assertEqual(po.order_line.product_id, product)
        self.assertEqual(po.order_line.product_qty, 30)
        self.assertEqual(po.order_line.int_source_sale_line_id, order.order_line)
        activity = po.activity_ids.filtered(lambda item: item.user_id == self.casey)
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity.summary, "Finish PO and send to Victron")

        activity.action_feedback(feedback="Reviewed")
        self.assertFalse(po.activity_ids)

        free_after = product.with_context(warehouse_id=self.warehouse.id).free_qty
        second = self._order(product, free_after + 4)
        second.action_confirm()
        po.invalidate_recordset()
        self.assertEqual(len(po.order_line), 2)
        added = po.order_line.filtered(lambda line: line.int_source_sale_line_id == second.order_line)
        self.assertEqual(added.product_qty, 4)
        self.assertEqual(
            len(po.activity_ids.filtered(lambda item: item.user_id == self.casey)),
            1,
        )

        second._action_cancel()
        self.assertFalse(added.exists())
        self.assertTrue(po.order_line)

    def test_mixed_cart_defaults_to_two_shipments_until_the_customer_chooses(self):
        product = self._product("Blue Solar", on_hand=17, victron=45)
        order = self._order(product, 20)
        order.picking_policy = "one"
        order._int_victron_default_ship_policy()
        self.assertEqual(order.picking_policy, "direct")
        self.assertTrue(order._int_victron_needs_ship_choice())

        order.int_ship_policy_chosen = True
        order.picking_policy = "one"
        order._int_victron_default_ship_policy()
        self.assertEqual(order.picking_policy, "one")

    def test_backorder_does_not_add_a_second_shipping_charge(self):
        product = self._product("Blue Solar", on_hand=2, victron=0)
        carrier = self.env["delivery.carrier"].create({
            "name": "Victron Test Carrier",
            "delivery_type": "fixed",
            "product_id": self.env["product.product"].create({
                "name": "Victron Test Delivery",
                "type": "service",
            }).id,
            "fixed_price": 40.0,
            "invoice_policy": "real",
        })
        order = self._order(product, 2)
        delivery = order._create_delivery_line(carrier, 40.0)
        order.action_confirm()
        # Real-cost carriers store 0 until the first shipment. Checkout has already
        # charged 40 for the whole order; a follow-up shipment must leave that alone.
        delivery.price_unit = 40.0
        picking = order.picking_ids[:1]
        backorder = self.env["stock.picking"].create({
            "picking_type_id": picking.picking_type_id.id,
            "location_id": picking.location_id.id,
            "location_dest_id": picking.location_dest_id.id,
            "partner_id": order.partner_shipping_id.id,
            "backorder_id": picking.id,
            "carrier_id": carrier.id,
            "carrier_price": 18.0,
            "sale_id": order.id,
        })
        backorder._add_delivery_cost_to_so()
        charges = order.order_line.filtered("is_delivery")
        self.assertEqual(charges, delivery)
        self.assertEqual(delivery.price_unit, 40.0)
