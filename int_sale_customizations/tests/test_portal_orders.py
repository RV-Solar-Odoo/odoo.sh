from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalOrders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.int_max_pinned = 1
        cls.product = cls.env["product.product"].create({
            "name": "Portal order service",
            "type": "service",
            "list_price": 15,
            "sale_ok": True,
            "default_code": "INT-PORTAL-SVC",
        })
        if "is_published" in cls.product.product_tmpl_id._fields:
            cls.product.product_tmpl_id.is_published = True

    def _order(self, partner, name_ref="PO-1"):
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "client_order_ref": name_ref,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        order.action_confirm()
        return order

    def _portal(self, partner, login, role):
        partner.sudo().write({"int_portal_role": role})
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name,
            "login": login,
            "email": login,
            "partner_id": partner.id,
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
        })

    def test_search_domain_uses_order_date_and_each_field(self):
        dealer = self.env["res.partner"].create({"name": "Search Dealer", "is_company": True})
        order = self._order(dealer, "PO-SEARCH")
        SaleOrder = self.env["sale.order"]
        by_name = SaleOrder._int_portal_order_domain(dealer, search=order.name, search_in="name")
        self.assertIn(order, SaleOrder.search(by_name))
        by_po = SaleOrder._int_portal_order_domain(dealer, search="PO-SEARCH", search_in="po")
        self.assertIn(order, SaleOrder.search(by_po))
        by_sku = SaleOrder._int_portal_order_domain(dealer, search="INT-PORTAL-SVC", search_in="product")
        self.assertIn(order, SaleOrder.search(by_sku))
        dated = SaleOrder._int_portal_order_domain(dealer, date_begin="2000-01-01", date_end="2000-01-02")
        self.assertNotIn(order, SaleOrder.search(dated))

    def test_serial_search_stays_inside_the_dealer(self):
        dealer = self.env["res.partner"].create({"name": "Serial Dealer", "is_company": True})
        other = self.env["res.partner"].create({"name": "Other Dealer", "is_company": True})
        buyer = self._portal(dealer, "serial-buyer@example.com", "buyer")
        SaleOrder = self.env["sale.order"]
        self.assertEqual(SaleOrder.with_user(buyer)._int_serial_order_ids(other, "SECRET-LOT"), [])

    def test_po_rows_and_unknown_sku(self):
        rows = [
            ["PO Number", "PO-9"],
            [],
            ["SKU", "Qty"],
            ["INT-PORTAL-SVC", 2],
            ["MISSING", "nope"],
            ["", 1],
        ]
        po_number, parsed = self.env["sale.order"]._int_po_rows(rows)
        self.assertEqual(po_number, "PO-9")
        self.assertEqual(parsed[0], ("INT-PORTAL-SVC", 2))
        added, rejected = self.env["sale.order"]._int_match_po_rows(parsed, False)
        self.assertTrue(added)
        self.assertEqual(added[0][0].default_code, "INT-PORTAL-SVC")
        self.assertEqual(len(rejected), 2)

    def test_pinned_orders_sort_first(self):
        dealer = self.env["res.partner"].create({"name": "Pin Sort Dealer", "is_company": True})
        self.company.int_max_pinned = 5
        older = self._order(dealer, "PIN-OLD")
        middle = self._order(dealer, "PIN-MID")
        newer = self._order(dealer, "PIN-NEW")
        older.date_order = "2026-01-01"
        middle.date_order = "2026-06-01"
        newer.date_order = "2026-11-01"
        user = self._portal(dealer, "pin-sort@example.com", "buyer")
        self.assertEqual(user.int_portal_toggle_pin(older), "pinned")
        SaleOrder = self.env["sale.order"].with_user(user)
        domain = SaleOrder._int_portal_order_domain(dealer)
        order = "date_order desc, id desc"
        page = SaleOrder._int_portal_orders_page(domain, order, user.int_pinned_order_ids.ids, 2, 0)
        self.assertEqual(list(page), [older, newer])
        rest = SaleOrder._int_portal_orders_page(domain, order, user.int_pinned_order_ids.ids, 2, 2)
        self.assertEqual(list(rest), [middle])
        cancelled = SaleOrder._int_portal_order_domain(dealer, filterby="cancelled")
        hidden = SaleOrder._int_portal_orders_page(cancelled, order, user.int_pinned_order_ids.ids, 20, 0)
        self.assertNotIn(older, hidden)

    def test_pin_limit(self):
        user = self.env.user
        first = self._order(user.partner_id, "PIN-1")
        second = self._order(user.partner_id, "PIN-2")
        self.assertEqual(user.int_portal_toggle_pin(first), "pinned")
        with self.assertRaises(UserError):
            user.int_portal_toggle_pin(second)
        self.assertEqual(user.int_portal_toggle_pin(first), "unpinned")

    def test_cancel_request_does_not_cancel_and_confirm_is_once(self):
        partner = self.env["res.partner"].create({"name": "Cancel Dealer", "is_company": True})
        user = self._portal(partner, "cancel-owner@example.com", "owner")
        order = self._order(partner, "CANCEL-1")
        order.int_portal_request_cancel(user, "delay", "please", "")
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.int_cancel_state, "requested")
        order.int_confirm_cancellation(self.env.user, "store_credit", "ok")
        self.assertEqual(order.state, "cancel")
        self.assertTrue(order.int_cancel_settled)
        with self.assertRaises(UserError):
            order.int_confirm_cancellation(self.env.user, "original", "again")

    def test_deny_needs_a_note_and_can_be_requested_again(self):
        partner = self.env["res.partner"].create({"name": "Deny Dealer", "is_company": True})
        user = self._portal(partner, "deny-owner@example.com", "owner")
        order = self._order(partner, "DENY-1")
        order.int_portal_request_cancel(user, "other", "", "")
        with self.assertRaises(UserError):
            order.int_deny_cancellation(self.env.user, "  ")
        order.int_deny_cancellation(self.env.user, "Keep it")
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.int_cancel_state, "denied")
        order.int_portal_request_cancel(user, "delay", "", "")
        self.assertEqual(order.int_cancel_state, "requested")

    def test_export_header_includes_the_address_columns(self):
        header = self.env["sale.order"]._int_export_header()
        for column in ("Order #", "Serial #s", "Dock", "Forklift", "Commercial/Residential", "Delivery method"):
            self.assertIn(column, header)

    def test_export_rows_are_products_only_with_the_delivery_method(self):
        goods = self.env["product.product"].create({
            "name": "Export battery", "type": "consu", "list_price": 100, "default_code": "INT-EXP-BAT",
        })
        shipping = self.env["product.product"].create({"name": "Export shipping", "type": "service", "list_price": 0})
        discount = self.env["product.product"].create({"name": "Export discount", "type": "service", "list_price": -10})
        carrier = self.env["delivery.carrier"].create({
            "name": "Export Ground", "delivery_type": "fixed", "fixed_price": 12, "product_id": shipping.id,
        })
        order = self.env["sale.order"].create({
            "partner_id": self.env["res.partner"].create({"name": "Export Dealer"}).id,
            "carrier_id": carrier.id,
            "order_line": [
                Command.create({"product_id": goods.id, "product_uom_qty": 2}),
                Command.create({"product_id": shipping.id, "name": "Export Ground", "price_unit": 12, "is_delivery": True}),
                Command.create({"product_id": discount.id, "price_unit": -10}),
                Command.create({"display_type": "line_note", "name": "Leave at the dock"}),
            ],
        })
        header = order._int_export_header()
        rows = order._int_export_rows()
        self.assertEqual([row[header.index("SKU")] for row in rows], ["INT-EXP-BAT"])
        self.assertEqual(rows[0][header.index("Delivery method")], "Export Ground")
        self.assertEqual(len(rows[0]), len(header))
        addable, skipped = order._int_reorder_plan(self.env["website"].search([], limit=1))
        self.assertNotIn("Export shipping", [line.product_id.name for line in addable])
        self.assertNotIn("Export shipping", [name for name, _reason in skipped])

    def test_buyer_cannot_read_invoices(self):
        dealer = self.env["res.partner"].create({"name": "Invoice Dealer", "is_company": True})
        buyer = self._portal(
            self.env["res.partner"].create({
                "name": "Invoice Buyer",
                "parent_id": dealer.id,
                "email": "invoice-buyer@example.com",
            }),
            "invoice-buyer@example.com",
            "buyer",
        )
        owner = self._portal(dealer, "invoice-owner@example.com", "owner")
        income = self.env["account.account"].search([
            ("account_type", "=", "income"),
            ("company_ids", "in", self.company.id),
        ], limit=1)
        self.assertTrue(income)
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": dealer.id,
            "invoice_line_ids": [Command.create({
                "name": "Hidden from buyer",
                "quantity": 1,
                "price_unit": 10,
                "account_id": income.id,
                "tax_ids": [Command.clear()],
            })],
        })
        invoice.action_post()
        buyer_invoices = self.env["account.move"].with_user(buyer).search([("id", "=", invoice.id)])
        owner_invoices = self.env["account.move"].with_user(owner).search([("id", "=", invoice.id)])
        self.assertFalse(buyer_invoices)
        self.assertIn(invoice, owner_invoices)

    def test_order_page_actions_stay_on_the_html_portal(self):
        arch = self.env.ref("sale.sale_order_portal_content").get_combined_arch()
        self.assertIn("report_type != 'pdf'", arch)
        self.assertNotIn('t-if="not report_type"', arch)
        self.assertIn('t-set="order" t-value="sale_order"', arch)
        self.assertIn('id="int_cancel_modal"', arch)
        self.assertIn('data-bs-toggle="modal"', arch)
        self.assertIn("Request cancellation", arch)
