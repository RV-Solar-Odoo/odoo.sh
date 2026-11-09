from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalAccount(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        cls.warehouse = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.company.id),
        ], limit=1)
        cls.customers = cls.env.ref("stock.stock_location_customers")

    def _partner(self, name, **extra):
        values = {"name": name, "company_id": self.company.id}
        values.update(extra)
        return self.env["res.partner"].create(values)

    def _portal_user(self, partner, login, role):
        partner.sudo().int_portal_role = role
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name,
            "login": login,
            "email": login,
            "partner_id": partner.id,
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
        })

    def _limit(self, partner, amount):
        partner.with_company(self.company).sudo().credit_limit = amount

    def _picking(self, **extra):
        values = {
            "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.warehouse.lot_stock_id.id,
            "location_dest_id": self.customers.id,
        }
        values.update(extra)
        return self.env["stock.picking"].create(values)

    def test_credit_figures_match_the_stated_rules(self):
        Users = self.env["res.users"]
        under = Users._int_portal_credit_figures(50, 0, 100, self.currency)
        self.assertEqual(under["level"], "ok")
        self.assertEqual(under["available"], 50)
        near = Users._int_portal_credit_figures(80, 0, 100, self.currency)
        self.assertEqual(near["level"], "warn")
        over = Users._int_portal_credit_figures(80, 30, 100, self.currency)
        self.assertEqual(over["used"], 110)
        self.assertEqual(over["available"], 0)
        self.assertEqual(over["over"], 10)
        self.assertEqual(over["level"], "over")
        self.assertEqual(over["percent"], 100)
        balance = Users._int_portal_credit_figures(-30, 10, 100, self.currency)
        self.assertEqual(balance["credit_on_account"], 30)
        self.assertEqual(balance["used"], 10)
        self.assertEqual(balance["available"], 90)

    def test_credit_card_follows_the_role_and_the_company_switch(self):
        self.company.account_use_credit_limit = True
        dealer = self._partner("Credit Dealer Co", is_company=True)
        self._limit(dealer, 1000)
        owner = self._portal_user(dealer, "owner-credit-portal@example.com", "owner")
        self.assertTrue(owner._int_portal_credit())
        accountant = self._partner("Credit Accountant", parent_id=dealer.id, email="acct-credit-portal@example.com")
        accountant_user = self._portal_user(accountant, "acct-credit-portal@example.com", "accountant")
        self.assertTrue(accountant_user._int_portal_credit())
        buyer = self._partner("Credit Buyer", parent_id=dealer.id, email="buyer-credit-portal@example.com")
        buyer_user = self._portal_user(buyer, "buyer-credit-portal@example.com", "buyer")
        self.assertFalse(buyer_user._int_portal_credit())
        viewer = self._partner("Credit Viewer", parent_id=dealer.id, email="viewer-credit-portal@example.com")
        viewer_user = self._portal_user(viewer, "viewer-credit-portal@example.com", "viewer")
        self.assertFalse(viewer_user._int_portal_credit())
        self._limit(dealer, 0)
        self.assertFalse(owner._int_portal_credit())
        self._limit(dealer, 1000)
        self.company.account_use_credit_limit = False
        self.assertFalse(owner._int_portal_credit())

    def test_internal_user_can_see_credit_whatever_the_role(self):
        self.company.account_use_credit_limit = True
        partner = self._partner("Staff Credit")
        self._limit(partner, 500)
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Staff Credit",
            "login": "staff-credit-portal@example.com",
            "email": "staff-credit-portal@example.com",
            "partner_id": partner.id,
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_user").id])],
        })
        partner.sudo().int_portal_role = "buyer"
        self.assertTrue(user._int_portal_credit())

    def test_credit_matches_an_open_invoice_and_an_uninvoiced_order(self):
        self.company.account_use_credit_limit = True
        partner = self._partner("Invoiced Dealer", is_company=True)
        self._limit(partner, 1000)
        user = self._portal_user(partner, "invoiced-dealer-portal@example.com", "owner")
        income = self.env["account.account"].search([
            ("account_type", "=", "income"),
            ("company_ids", "in", self.company.id),
        ], limit=1)
        if not income:
            income = self.env["account.account"].search([
                ("account_type", "=", "income"),
            ], limit=1)
        self.assertTrue(income)
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [Command.create({
                "name": "Open invoice",
                "quantity": 1,
                "price_unit": 40,
                "account_id": income.id,
                "tax_ids": [Command.clear()],
            })],
        })
        invoice.action_post()
        product = self.env["product.product"].create({
            "name": "Uninvoiced portal service",
            "type": "service",
            "list_price": 25,
            "invoice_policy": "order",
            "taxes_id": [Command.clear()],
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": 1,
                "price_unit": 25,
            })],
        })
        order.action_confirm()
        info = user._int_portal_credit()
        commercial = partner.with_company(self.company).sudo()
        self.assertGreater(commercial.credit, 0)
        self.assertGreater(commercial.credit_to_invoice, 0)
        self.assertAlmostEqual(info["used"], commercial.credit + commercial.credit_to_invoice, places=2)
        self.assertAlmostEqual(info["limit"], commercial.credit_limit, places=2)

    def test_sales_rep_comes_from_the_company_contact(self):
        rep = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Casey Rep",
            "login": "casey-rep-portal@example.com",
            "email": "casey.rep.portal@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_user").id])],
        })
        rep.partner_id.sudo().phone = "555-0100"
        dealer = self._partner("Rep Dealer Co", is_company=True, user_id=rep.id)
        self.assertFalse(self._portal_user(
            self._partner("No Rep Co", is_company=True),
            "no-rep-portal@example.com",
            "owner",
        )._int_portal_sales_rep())
        child = self._partner(
            "Extra Login",
            parent_id=dealer.id,
            email="extra-login-portal@example.com",
        )
        shown = self._portal_user(child, "extra-login-portal@example.com", "viewer")._int_portal_sales_rep()
        self.assertEqual(shown["name"], "Casey Rep")
        self.assertEqual(shown["email"], "casey.rep.portal@example.com")
        self.assertEqual(shown["phone"], "555-0100")
        self.assertEqual(shown["phone_href"], "tel:5550100")

    def test_tracking_links_cover_missing_partial_and_several_shipments(self):
        self.assertTrue(self.warehouse)
        bare = self._picking()
        self.assertFalse(bare._int_portal_tracking_links())
        plain = self._picking(carrier_tracking_ref="PLAIN1")
        plain_links = plain._int_portal_tracking_links()
        self.assertEqual(plain_links, [{"number": "PLAIN1", "url": False}])
        split = self._picking(carrier_tracking_ref="111, 222")
        self.assertEqual(
            [link["number"] for link in split._int_portal_tracking_links()],
            ["111", "222"],
        )
        self.assertFalse(any(link["url"] for link in split._int_portal_tracking_links()))
        carrier = self.env["delivery.carrier"].create({
            "name": "Portal Test Carrier",
            "delivery_type": "fixed",
            "product_id": self.env.ref("delivery.product_product_delivery").id,
            "fixed_price": 0,
            "tracking_url": "https://track.example/<shipmenttrackingnumber>",
        })
        linked = self._picking(carrier_id=carrier.id, carrier_tracking_ref="ABC123")
        self.assertEqual(linked._int_portal_tracking_links(), [{
            "number": "ABC123",
            "url": "https://track.example/ABC123",
        }])
        combined = self._picking(carrier_id=carrier.id, carrier_tracking_ref="111, 222")
        combined_links = combined._int_portal_tracking_links()
        self.assertEqual([link["number"] for link in combined_links], ["111", "222"])
        self.assertFalse(any(link["url"] for link in combined_links))
        json_carrier = self.env["delivery.carrier"].create({
            "name": "Portal JSON Carrier",
            "delivery_type": "fixed",
            "product_id": self.env.ref("delivery.product_product_delivery").id,
            "fixed_price": 0,
            "tracking_url": '[["<shipmenttrackingnumber>", "https://track.example/<shipmenttrackingnumber>"]]',
        })
        paired = self._picking(carrier_id=json_carrier.id, carrier_tracking_ref="JSON1")
        self.assertEqual(paired._int_portal_tracking_links(), [{
            "number": "JSON1",
            "url": "https://track.example/JSON1",
        }])

        product = self.env["product.product"].create({
            "name": "Shipped portal item",
            "type": "consu",
            "is_storable": True,
            "list_price": 5,
        })
        order = self.env["sale.order"].create({
            "partner_id": self._partner("Ship Dealer").id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": 1,
            })],
        })
        self.assertFalse(order._int_portal_shipments()[order.id]["links"])
        self.assertFalse(order._int_portal_shipments()[order.id]["partial"])
        order.action_confirm()
        outgoing = order.picking_ids.filtered(lambda picking: picking.picking_type_code == "outgoing")
        self.assertTrue(outgoing)
        first = outgoing[0]
        first.write({
            "carrier_id": carrier.id,
            "carrier_tracking_ref": "SHIP1",
            "state": "done",
        })
        shipped = order._int_portal_shipments()[order.id]
        self.assertEqual(shipped["links"], [{
            "number": "SHIP1",
            "url": "https://track.example/SHIP1",
        }])
        self.assertFalse(shipped["partial"])
        second = self._picking()
        self.env["stock.move"].create({
            "name": product.name,
            "product_id": product.id,
            "product_uom_qty": 1,
            "product_uom": product.uom_id.id,
            "picking_id": second.id,
            "location_id": second.location_id.id,
            "location_dest_id": second.location_dest_id.id,
            "sale_line_id": order.order_line.id,
        })
        partial = order._int_portal_shipments()[order.id]
        self.assertTrue(partial["partial"])
        self.assertEqual(len(partial["shipments"]), 2)
        self.assertEqual(partial["links"][0]["number"], "SHIP1")
