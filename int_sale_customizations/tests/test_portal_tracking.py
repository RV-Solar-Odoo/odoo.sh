from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalTracking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.company.id),
        ], limit=1)
        cls.customers = cls.env.ref("stock.stock_location_customers")

    def _partner(self, name, **extra):
        values = {"name": name, "company_id": self.company.id}
        values.update(extra)
        return self.env["res.partner"].create(values)

    def _picking(self, **extra):
        values = {
            "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.warehouse.lot_stock_id.id,
            "location_dest_id": self.customers.id,
        }
        values.update(extra)
        return self.env["stock.picking"].create(values)

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

    def test_tracking_links_open_in_a_new_tab(self):
        from lxml import etree

        arch = etree.fromstring(self.env.ref("int_sale_customizations.portal_tracking_links").get_combined_arch())
        links = arch.xpath("//a")
        self.assertTrue(links)
        for link in links:
            self.assertEqual(link.get("target"), "_blank")
            self.assertIn("noopener", link.get("rel") or "")
        # My Orders and the order page both draw their links with that template.
        for xmlid in (
            "int_sale_customizations.portal_my_orders_tracking",
            "int_sale_customizations.portal_delivery_tracking_links",
        ):
            self.assertIn("int_sale_customizations.portal_tracking_links", self.env.ref(xmlid).arch)
