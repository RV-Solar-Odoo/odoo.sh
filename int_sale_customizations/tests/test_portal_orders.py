import base64

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalOrders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
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

    def test_po_upload_reads_common_columns_and_text(self):
        SaleOrder = self.env["sale.order"]
        rows = [
            ["P.O. #", "PO-77"],
            [],
            ["Part Number", "Qty Ordered"],
            ["int-portal-svc", "2 pcs"],
            ["INT-PORTAL-SVC", "nope"],
        ]
        po_number, parsed = SaleOrder._int_po_rows(rows)
        self.assertEqual(po_number, "PO-77")
        self.assertEqual(parsed[0], ("int-portal-svc", "2 pcs"))
        added, rejected = SaleOrder._int_match_po_rows(parsed, False)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0][1], 2)
        self.assertEqual(len(rejected), 1)
        self.product.barcode = "BC-PORTAL-1"
        barcode_po, barcode_rows = SaleOrder._int_po_rows([
            ["UPC", "Quantity"],
            ["bc portal 1", 1],
        ])
        added, rejected = SaleOrder._int_match_po_rows(barcode_rows, False)
        self.assertFalse(barcode_po)
        self.assertEqual(added[0][0], self.product)
        self.assertFalse(rejected)
        dashed = self.env["product.product"].create({
            "name": "Dashed portal product",
            "type": "service",
            "list_price": 5,
            "sale_ok": True,
            "default_code": "ABC-123",
        })
        if "is_published" in dashed.product_tmpl_id._fields:
            dashed.product_tmpl_id.is_published = True
        added, rejected = SaleOrder._int_match_po_rows([("ABC123", 3)], False)
        self.assertEqual(added[0][0], dashed)
        self.assertFalse(rejected)
        twin = dashed.copy({"default_code": "DUP-1"})
        dashed.default_code = "DUP-1"
        if "is_published" in twin.product_tmpl_id._fields:
            twin.product_tmpl_id.is_published = True
        added, rejected = SaleOrder._int_match_po_rows([("DUP-1", 1)], False)
        self.assertFalse(added)
        self.assertIn("More than one", rejected[0][1])
        text_po, text_lines = SaleOrder._int_po_review_from_text(
            "PO Number: PO-44\nINT-PORTAL-SVC 4\nNO-SUCH-99 1\n",
            False,
        )
        self.assertEqual(text_po, "PO-44")
        matched = [line for line in text_lines if line["product_id"]]
        self.assertEqual(matched[0]["qty"], 4)
        self.assertTrue(any(line["sku"] == "NO-SUCH-99" and line["reason"] for line in text_lines))
        with self.assertRaises(UserError):
            SaleOrder._int_po_rows([["SKU", "Qty"]] + [["X", 1]] * 501)
        orders = str(self.env.ref("sale.portal_my_orders").get_combined_arch())
        self.assertIn("PO #", orders)
        review = self.env.ref("int_sale_customizations.portal_po_review").arch
        self.assertIn("/my/po-upload/confirm", review)

    def test_po_upload_reads_real_purchase_order_layouts(self):
        SaleOrder = self.env["sale.order"]
        po_number, rows = SaleOrder._int_po_rows([
            ["Purchase Order", "4500018392", "Document Date", "11/26/2026"],
            [],
            ["Item", "Material", "Short Text", "Order Quantity", "Un", "Net Price"],
            ["10", "INT-PORTAL-SVC", "Portal order service", 4, "EA", 15],
            ["20", "NO-SUCH", "Missing", 1, "EA", 1],
        ])
        self.assertEqual(po_number, "4500018392")
        added, rejected = SaleOrder._int_match_po_rows(rows, False)
        self.assertEqual(added[0][0].default_code, "INT-PORTAL-SVC")
        self.assertEqual(added[0][1], 4)
        self.assertEqual(len(rejected), 1)

        po_number, rows = SaleOrder._int_po_rows([
            ["PURCHASE ORDER"],
            ["High Country RV"],
            ["DATE", "PO #"],
            ["11/26/2026", "PO-88421"],
            [],
            ["ITEM #", "DESCRIPTION", "QTY", "UNIT PRICE", "TOTAL"],
            ["INT-PORTAL-SVC", "Portal order service", 2, 15, 30],
            ["SUBTOTAL", "", "", "", 30],
        ])
        self.assertEqual(po_number, "PO-88421")
        added, rejected = SaleOrder._int_match_po_rows(rows, False)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0][1], 2)
        self.assertFalse(rejected)

        po_number, rows = SaleOrder._int_po_rows([
            ["po-number", "line-number", "source-part-num", "description", "quantity", "uom", "price"],
            ["PO-61094", "1", "INT-PORTAL-SVC", "Service", "3", "EA", "15"],
        ])
        self.assertEqual(po_number, "PO-61094")
        added, rejected = SaleOrder._int_match_po_rows(rows, False)
        self.assertEqual(added[0][1], 3)

        po_number, rows = SaleOrder._int_po_rows([
            ["Item Code", "Description", "Quantity", "Unit Price", "Disc %", "Amount"],
            ["INT-PORTAL-SVC", "Portal order service", 2, 15, "0%", 30],
        ])
        self.assertFalse(po_number)
        added, rejected = SaleOrder._int_match_po_rows(rows, False)
        self.assertEqual(added[0][1], 2)
        self.assertFalse(rejected)
        added, rejected = SaleOrder._int_match_po_rows([
            ("Services : Portal : INT-PORTAL-SVC", 5),
        ], False)
        self.assertEqual(added[0][0].default_code, "INT-PORTAL-SVC")
        self.assertEqual(added[0][1], 5)
        self.assertFalse(rejected)

        po_number, rows = SaleOrder._int_po_rows([
            ["PO Number", "Line", "Qty Ord", "UOM", "Manufacturer Part Number", "Description"],
            ["PO-WH-441", "1", "6", "EA", "int-portal-svc", "Service"],
        ])
        self.assertEqual(po_number, "PO-WH-441")
        added, rejected = SaleOrder._int_match_po_rows(rows, False)
        self.assertEqual(added[0][1], 6)

        text_po, lines = SaleOrder._int_po_review_from_text("\n".join([
            "PURCHASE ORDER",
            "PO Box 500",
            "P.O. No. 2026-114",
            "Product/Service SKU Description Qty Rate Amount",
            "MultiPlus-II 48/3000/35-50 120V (UL 1741) INT-PORTAL-SVC Portal order service 4 1,249.00 4,996.00",
            "Subtotal 4,996.00",
        ]), False)
        self.assertEqual(text_po, "2026-114")
        matched = [line for line in lines if line["product_id"]]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["qty"], 4)
        self.assertFalse(any(line["sku"] == "120V" for line in lines))
        wrapped_po, wrapped = SaleOrder._int_po_review_from_text("\n".join([
            "P.O. No. QB-33018",
            "MultiPlus-II 48/3000/35-50 120V (UL",
            "1741)",
            "INT-PORTAL-SVC Portal order service 4 1,249.00",
        ]), False)
        self.assertEqual(wrapped_po, "QB-33018")
        self.assertEqual([line["qty"] for line in wrapped if line["product_id"]], [4])
        self.assertFalse(any(line["sku"] == "120V" for line in wrapped))
        joined = self.env["sale.order"]._int_po_join_rows([
            (40, 100, "P.O. NO."),
            (400, 99, "QB-33018"),
            (40, 80, "INT-PORTAL-SVC"),
            (300, 80, "4"),
            (360, 80, "1,249.00"),
            (40, 60, "12/4k/160-50"),
        ])
        joined_po, joined_lines = SaleOrder._int_po_review_from_text(joined, False)
        self.assertEqual(joined_po, "QB-33018")
        matched = [line for line in joined_lines if line["product_id"]]
        self.assertEqual(matched[0]["qty"], 4)
        self.assertFalse(any(line["sku"] in ("QB-33018", "12/4k/160-50") for line in joined_lines))
        bare_po, bare_lines = SaleOrder._int_po_review_from_text(
            "No. PO-5005\nINT-PORTAL-SVC 1 15.00\n",
            False,
        )
        self.assertEqual(bare_po, "PO-5005")
        self.assertEqual([line["qty"] for line in bare_lines if line["product_id"]], [1])

    def test_uploaded_po_file_stays_on_the_order(self):
        partner = self.env["res.partner"].create({"name": "PO File Dealer", "is_company": True})
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        attachment = self.env["ir.attachment"].create({
            "name": "dealer-po.pdf",
            "datas": base64.b64encode(b"%PDF-1.4"),
            "type": "binary",
        })
        order._int_po_keep_file(attachment)
        self.assertEqual(order.int_po_attachment_id, attachment)
        self.assertEqual(attachment.res_model, "sale.order")
        self.assertEqual(attachment.res_id, order.id)
        self.assertFalse(attachment.public)
        self.assertIn(attachment, order.message_ids.attachment_ids)
        order._int_po_keep_file(attachment)
        linked = order.message_ids.filtered(lambda message: attachment in message.attachment_ids)
        self.assertEqual(len(linked), 1)
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(attachment.res_id, order.id)
        self.assertEqual(order._int_po_portal_file(), "dealer-po.pdf")

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
