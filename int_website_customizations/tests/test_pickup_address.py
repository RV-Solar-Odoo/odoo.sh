from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestPickupContact(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        cls.customer = cls.env["res.partner"].create({
            "name": "Annie King",
            "email": "annie@example.com",
            "phone": "435-555-0100",
        })
        cls.placeholder = cls.env["res.partner"].create({
            "name": "Anonymous express checkout partner for order TEST",
            "type": "delivery",
            "parent_id": cls.customer.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Pickup product",
            "type": "consu",
            "is_storable": True,
            "list_price": 20,
        })
        cls.delivery_product = cls.env["product.product"].create({
            "name": "Pick up in store",
            "type": "service",
            "sale_ok": False,
            "list_price": 0,
        })
        cls.carrier = cls.env["delivery.carrier"].create({
            "name": "Pick up in store",
            "delivery_type": "in_store",
            "product_id": cls.delivery_product.id,
            "warehouse_ids": [Command.set(cls.warehouse.ids)],
        })
        cls.fiscal_position = cls.env["account.fiscal.position"].create({
            "name": "Pickup tax location",
            "company_id": cls.env.company.id,
        })

    def _order(self, carrier=None):
        return self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "partner_invoice_id": self.customer.id,
            "partner_shipping_id": self.placeholder.id,
            "warehouse_id": self.warehouse.id,
            "carrier_id": (carrier or self.carrier).id,
            "fiscal_position_id": self.fiscal_position.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })

    def test_in_store_pickup_keeps_the_customer_as_the_delivery_contact(self):
        order = self._order()
        pickup_data = {
            "id": self.warehouse.id,
            "name": "RVSB",
            "street": "335 Commerce St",
            "city": "Hurricane",
            "state": "UT",
            "zip_code": "84737",
            "country_code": "US",
        }
        order.pickup_location_data = pickup_data
        pickup_count = self.env["res.partner"].search_count([
            ("is_pickup_location", "=", True),
        ])

        order.action_confirm()

        self.assertEqual(order.partner_shipping_id, self.customer)
        self.assertEqual(order.picking_ids.partner_id, self.customer)
        self.assertEqual(order.warehouse_id, self.warehouse)
        self.assertEqual(order.fiscal_position_id, self.fiscal_position)
        self.assertEqual(order.pickup_location_data, pickup_data)
        self.assertEqual(
            self.env["res.partner"].search_count([
                ("is_pickup_location", "=", True),
            ]),
            pickup_count,
        )
        self.assertFalse(self.placeholder.active)

    def test_shipping_order_keeps_its_delivery_address(self):
        shipping_product = self.delivery_product.copy({"name": "Shipping fee"})
        carrier = self.env["delivery.carrier"].create({
            "name": "Ground",
            "delivery_type": "fixed",
            "fixed_price": 0,
            "product_id": shipping_product.id,
        })
        order = self._order(carrier)

        order.action_confirm()

        self.assertEqual(order.partner_shipping_id, self.placeholder)
        self.assertEqual(order.picking_ids.partner_id, self.placeholder)
        self.assertTrue(self.placeholder.active)
