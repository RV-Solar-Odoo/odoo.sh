from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBackorders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.warehouse = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.website = env["website"].search([("company_id", "=", env.company.id)], limit=1) or env["website"].create({
            "name": "Backorder Test Website",
            "company_id": env.company.id,
        })
        cls.website.warehouse_id = cls.warehouse
        cls.customer = env["res.partner"].create({"name": "Backorder Customer"})
        cls.victron = env["res.partner"].create({"name": "Victron Backorder Vendor", "supplier_rank": 1})
        cls.supplier = env["res.partner"].create({"name": "Other Backorder Vendor", "supplier_rank": 1})
        cls.casey = env["res.users"].with_context(no_reset_password=True).create({
            "name": "Casey Backorders",
            "login": "casey.backorders.test",
            "email": "casey.backorders.test@example.com",
        })
        icp = env["ir.config_parameter"].sudo()
        icp.set_param("int_victron.vendor_partner_id", str(cls.victron.id))
        icp.set_param("int_victron.buyer_user_id", str(cls.casey.id))
        icp.set_param("int_victron.lead_time_label", "within 7–10 days")

    def setUp(self):
        super().setUp()
        self.env["product.template"]._int_victron_clear_po_cache()

    def _product(self, name, on_hand=0, victron=0, backorder=True, vendor=None, victron_sku=False):
        product = self.env["product.product"].create({
            "name": name,
            "type": "consu",
            "is_storable": True,
            "list_price": 100.0,
            "taxes_id": [Command.clear()],
            "allow_out_of_stock_order": backorder,
        })
        product.product_tmpl_id.victron_qty = victron
        if victron_sku:
            product.product_tmpl_id.victron_sku = victron_sku
        if vendor:
            self.env["product.supplierinfo"].create({
                "partner_id": vendor.id,
                "product_tmpl_id": product.product_tmpl_id.id,
                "price": 60.0,
            })
        if on_hand:
            self.env["stock.quant"]._update_available_quantity(product, self.warehouse.lot_stock_id, on_hand)
        return product

    def _cart(self, *lines):
        return self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "website_id": self.website.id,
            "warehouse_id": self.warehouse.id,
            "order_line": [
                Command.create({"product_id": product.id, "product_uom_qty": qty, "tax_ids": [Command.clear()]})
                for product, qty in lines
            ],
        })

    def test_stock_then_victron_then_backorder(self):
        mixed = self._product("Backorder Mixed", on_hand=2, victron=3)
        local = self._product("Backorder Local", on_hand=1)
        closed = self._product("Backorder Closed", on_hand=1, backorder=False)
        cart = self._cart((mixed, 7), (local, 3), (closed, 1))
        by_product = {line.product_id: line for line in cart.order_line}
        plan = cart._int_backorder_plan()
        self.assertEqual(plan, {by_product[mixed].id: 2.0, by_product[local].id: 2.0})
        self.assertEqual(
            by_product[mixed]._int_victron_cart_note(),
            "2 ship now · 3 ship within 7–10 days · 2 on backorder · no ETA yet",
        )
        self.assertEqual(by_product[local]._int_victron_cart_note(), "1 ship now · 2 on backorder · no ETA yet")
        self.assertTrue(cart._int_has_backorder())
        self.assertFalse(cart._allow_express_checkout())

        in_stock = self._cart((self._product("Backorder Plenty", on_hand=5), 2))
        self.assertFalse(in_stock._int_has_backorder())

    def test_shop_label_says_backorder_when_nothing_is_anywhere(self):
        product = self._product("Backorder Label")
        lines = product.product_tmpl_id._int_availability_lines(product)
        self.assertEqual([line["status"] for line in lines], ["immediate", "backorder"])
        self.assertEqual(lines[1]["text"], "Backorder · no ETA yet")
        self.assertEqual(lines[1]["qty"], "")
        closed = self._product("Backorder Label Closed", backorder=False)
        self.assertEqual(
            [line["status"] for line in closed.product_tmpl_id._int_availability_lines(closed)],
            ["immediate", "backup"],
        )

    def test_split_keeps_the_price_and_the_cart_merges_back(self):
        part = self._product("Backorder Part", on_hand=5)
        none = self._product("Backorder None")
        cart = self._cart((part, 7), (none, 3))
        cart._int_backorder_split()
        part_lines = cart.order_line.filtered(lambda line: line.product_id == part)
        self.assertEqual(sorted(part_lines.mapped("product_uom_qty")), [2.0, 5.0])
        back = part_lines.filtered("int_backorder")
        self.assertEqual(back.product_uom_qty, 2.0)
        self.assertTrue(back.name.endswith("Backorder"))
        self.assertEqual(set(part_lines.mapped("price_unit")), {100.0})
        none_line = cart.order_line.filtered(lambda line: line.product_id == none)
        self.assertTrue(none_line.int_backorder)
        self.assertEqual(cart._int_backorder_amount(), 500.0)
        self.assertEqual(cart._int_pay_now_amount(), cart.amount_total - 500.0)
        # Once split, nothing more is backordered on paper.
        self.assertFalse(cart._int_backorder_plan())

        cart.require_payment = True
        cart.prepayment_percent = 1.0
        self.assertEqual(cart._get_prepayment_required_amount(), cart._int_pay_now_amount())
        self.assertFalse(cart._is_paid())

        cart._int_backorder_merge()
        part_lines = cart.order_line.filtered(lambda line: line.product_id == part)
        self.assertEqual(part_lines.mapped("product_uom_qty"), [7.0])
        self.assertFalse(cart.order_line.filtered("int_backorder"))
        self.assertFalse(none_line.name.endswith("Backorder"))

        # Changing a split cart's backorder line updates the line it went back into.
        cart._int_backorder_split()
        back = cart.order_line.filtered(lambda line: line.product_id == part and line.int_backorder)
        line_id, quantity = cart._int_backorder_merge(back.id, 4)
        merged = cart.order_line.filtered(lambda line: line.product_id == part)
        self.assertEqual(line_id, merged.id)
        self.assertEqual(quantity, 9.0)

    def test_confirm_gives_backorders_their_own_delivery_and_a_draft_po(self):
        mixed = self._product("Backorder Ship", on_hand=2, victron=3, vendor=self.supplier)
        no_vendor = self._product("Backorder Orphan")
        victron_only = self._product("Backorder Victron SKU", victron_sku="BO-VIC-1")
        order = self._cart((mixed, 6), (no_vendor, 1), (victron_only, 2))
        order._int_backorder_split()
        order.action_confirm()
        backorders = order.order_line.filtered("int_backorder")
        self.assertEqual(len(backorders), 3)

        back_moves = backorders.move_ids
        other_moves = (order.order_line - backorders).move_ids
        self.assertTrue(back_moves)
        self.assertFalse(back_moves.picking_id & other_moves.picking_id)
        self.assertTrue(all(picking.backorder_id for picking in back_moves.picking_id))

        pos = order._int_backorder_purchase_orders()
        self.assertEqual(set(pos.mapped("state")), {"draft"})
        self.assertTrue(all(pos.mapped("int_backorder_po")))
        self.assertFalse(any(pos.mapped("int_victron_rfq")))
        self.assertEqual(pos.partner_id, self.supplier | self.victron)
        supplier_po = pos.filtered(lambda po: po.partner_id == self.supplier)
        self.assertEqual(supplier_po.order_line.product_qty, 1.0)
        self.assertEqual(supplier_po.user_id, self.casey)
        self.assertIn("Review backorder PO", supplier_po.activity_ids.mapped("summary"))
        self.assertTrue(order.message_ids.filtered(lambda msg: "has no vendor" in (msg.body or "")))
        # The Victron-covered units still go on the separate Victron shortfall RFQ.
        shortfall = order._int_victron_purchase_orders()
        self.assertTrue(shortfall)
        self.assertFalse(shortfall & pos)
        self.assertTrue(all(shortfall.mapped("int_victron_rfq")))

        second = self._cart((mixed, 1))
        second._int_backorder_split()
        second.action_confirm()
        self.assertEqual(second._int_backorder_purchase_orders(), supplier_po)
        self.assertEqual(sorted(supplier_po.order_line.mapped("product_qty")), [1.0, 1.0])

    def test_open_backorder_is_not_invoiced_or_counted_until_released(self):
        product = self._product("Backorder Invoice", on_hand=1, vendor=self.supplier)
        order = self._cart((product, 3))
        order._int_backorder_split()
        order.action_confirm()
        back = order.order_line.filtered("int_backorder")
        shipped = order.order_line - back
        self.assertTrue(order.int_has_open_backorder)
        self.assertEqual(back.qty_to_invoice, 0.0)
        self.assertEqual(back.amount_to_invoice, 0.0)
        self.assertEqual(back.untaxed_amount_to_invoice, 0.0)
        self.assertEqual(order.amount_to_invoice, shipped.amount_to_invoice)
        order._force_lines_to_invoice_policy_order()
        self.assertEqual(back.qty_to_invoice, 0.0)

        order.action_int_release_backorder()
        self.assertTrue(back.int_backorder_released)
        self.assertFalse(order.int_has_open_backorder)
        self.assertEqual(back.qty_to_invoice, 2.0)
        self.assertEqual(back.amount_to_invoice, 200.0)
        with self.assertRaises(UserError):
            order.action_int_release_backorder()

    def test_cancelling_backorder_lines_clears_moves_and_the_draft_po(self):
        product = self._product("Backorder Cancel", on_hand=1, vendor=self.supplier)
        order = self._cart((product, 3))
        order._int_backorder_split()
        order.action_confirm()
        back = order.order_line.filtered("int_backorder")
        po = order._int_backorder_purchase_orders()
        self.assertTrue(po)
        order._int_backorder_cancel(back, self.env.user)
        self.assertEqual(back.product_uom_qty, 0.0)
        self.assertEqual(set(back.move_ids.mapped("state")), {"cancel"})
        self.assertFalse(po.exists())
        kept = order.order_line - back
        self.assertEqual(kept.product_uom_qty, 1.0)
        self.assertEqual(order.state, "sale")

        # A confirmed backorder PO is left for purchasing to review.
        again = self._cart((product, 2))
        again._int_backorder_split()
        again.action_confirm()
        po = again._int_backorder_purchase_orders()
        po.button_confirm()
        again._int_backorder_cancel(again.order_line.filtered("int_backorder"), self.env.user)
        self.assertTrue(po.exists())
        self.assertTrue(po.message_ids.filtered(lambda msg: "cancelled backordered items" in (msg.body or "")))
