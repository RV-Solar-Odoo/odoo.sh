from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.int_shippo_customizations.controllers.main import IntShippoDelivery
from odoo.addons.int_shippo_customizations.models.shippo_api import ShippoApi
from odoo.addons.website_sale.tests.common import MockRequest


def _rate(provider, name, token, amount):
    return {
        "object_id": f"rate_{token}",
        "provider": provider,
        "amount": str(amount),
        "currency": "USD",
        "servicelevel": {"name": name, "token": token},
    }


RATES = [
    _rate("UPS", "Ground", "ups_ground", 12.50),
    _rate("UPS", "Ground Saver", "ups_ground_saver", 9.00),
    _rate("UPS", "2nd Day Air®", "ups_second_day_air", 40.00),
    _rate("UPS", "Next Day Air®", "ups_next_day_air", 80.00),
    _rate("FedEx", "FedEx Ground", "fedex_ground", 11.00),
    _rate("FedEx", "FedEx 2Day®", "fedex_2_day", 38.00),
    _rate("FedEx", "FedEx Standard Overnight®", "fedex_standard_overnight", 70.00),
    _rate("USPS", "Priority Mail", "usps_priority", 8.00),
]


@tagged("post_install", "-at_install")
class TestShippoCheckout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env["ir.config_parameter"].sudo().set_param("int_shippo.api_token", "shippo_test_token")
        cls.us = env.ref("base.us")

        def state(code):
            return env["res.country.state"].search([("country_id", "=", cls.us.id), ("code", "=", code)])

        cls.warehouse = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.warehouse.partner_id.write({
            "street": "335 Commerce St",
            "city": "Hurricane",
            "zip": "84737",
            "state_id": state("UT").id,
            "country_id": cls.us.id,
            "phone": "+1 435-555-0100",
        })
        cls.customer = env["res.partner"].create({
            "name": "Shippo Test Customer",
            "street": "350 5th Ave",
            "city": "New York",
            "zip": "10118",
            "state_id": state("NY").id,
            "country_id": cls.us.id,
            "phone": "+1 212-555-0100",
        })
        cls.cheap = env["product.product"].create({
            "name": "Shippo Test Shunt", "type": "consu", "list_price": 100.0, "weight": 1.0,
        })
        cls.pricey = env["product.product"].create({
            "name": "Shippo Test Inverter", "type": "consu", "list_price": 300.0, "weight": 20.0,
        })
        cls.ground = env.ref("int_shippo_customizations.delivery_carrier_shippo_ups_ground")
        cls.two_day = env.ref("int_shippo_customizations.delivery_carrier_shippo_ups_2day")
        cls.overnight = env.ref("int_shippo_customizations.delivery_carrier_shippo_ups_overnight")
        cls.shippo_methods = cls.ground | cls.two_day | cls.overnight

    def setUp(self):
        super().setUp()
        # The per-request rate cache lives on the cursor, which every test here shares.
        self.env.cr._int_shippo_rates = {}
        self.calls = []
        self.response = {"rates": RATES, "messages": []}
        patcher = patch.object(ShippoApi, "request", autospec=True, side_effect=self._fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake_request(self, api, method, path, payload=None, **kwargs):
        self.calls.append((method, path, payload))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    def _order(self, product, partner=None):
        return self.env["sale.order"].create({
            "partner_id": (partner or self.customer).id,
            "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1})],
        })

    def _new_request(self):
        self.env.cr._int_shippo_rates = {}

    def test_each_tier_quotes_the_cheapest_matching_service(self):
        order = self._order(self.cheap)
        self.assertEqual(self.ground.rate_shipment(order)["price"], 11.00)
        self.assertEqual(self.two_day.rate_shipment(order)["price"], 38.00)
        self.assertEqual(self.overnight.rate_shipment(order)["price"], 70.00)
        self.assertEqual(len(self.calls), 1, "Every tier should share one Shippo call")

    def test_ground_is_free_over_threshold_and_faster_tiers_are_not(self):
        order = self._order(self.pricey)
        self.assertEqual(self.ground.rate_shipment(order)["price"], 0.0)
        self.assertEqual(self.two_day.rate_shipment(order)["price"], 38.00)

    def test_fresh_quote_is_reused_on_the_next_page_load(self):
        order = self._order(self.cheap)
        self.ground.rate_shipment(order)
        self._new_request()
        self.ground.rate_shipment(order)
        self.assertEqual(len(self.calls), 1)

    def test_changing_the_cart_asks_shippo_again(self):
        order = self._order(self.cheap)
        self.ground.rate_shipment(order)
        self._new_request()
        order.order_line.product_uom_qty = 2
        self.ground.rate_shipment(order)
        self.assertEqual(len(self.calls), 2)

    def test_stale_quote_covers_a_shippo_outage(self):
        order = self._order(self.cheap)
        self.ground.rate_shipment(order)
        order.int_shippo_rate_date = fields.Datetime.now() - timedelta(hours=3)
        self._new_request()
        self.response = UserError("Shippo error 503: down")
        result = self.ground.rate_shipment(order)
        self.assertTrue(result["success"])
        self.assertEqual(result["price"], 11.00)

    def test_outage_without_a_quote_hides_shippo_methods(self):
        order = self._order(self.cheap)
        self.response = UserError("Shippo error 503: down")
        self.assertFalse(self.ground.rate_shipment(order)["success"])
        self.assertFalse(self.ground._is_available_for_order(order))

    def test_carrier_dropping_out_keeps_the_last_full_quote(self):
        order = self._order(self.cheap)
        self.ground.rate_shipment(order)
        order.int_shippo_rate_date = fields.Datetime.now() - timedelta(hours=3)
        self._new_request()
        self.response = {
            "rates": [r for r in RATES if r["provider"] != "FedEx"],
            "messages": [{"source": "FedEx", "text": "Rate limit exceeded"}],
        }
        self.assertEqual(self.ground.rate_shipment(order)["price"], 11.00)

    def test_ground_only_category_hides_faster_tiers(self):
        if "ground_shipping_only" not in self.env["product.category"]._fields:
            self.skipTest("int_inventory_customizations is not installed")
        category = self.env["product.category"].create({
            "name": "Shippo Test Batteries", "ground_shipping_only": True,
        })
        self.cheap.categ_id = category
        order = self._order(self.cheap)
        self.assertTrue(self.ground._is_available_for_order(order))
        self.assertFalse(self.two_day._is_available_for_order(order))
        self.assertFalse(self.overnight._is_available_for_order(order))

    def test_no_message_when_a_shipped_method_is_offered(self):
        order = self._order(self.cheap)
        self.assertFalse(order._int_shipping_unavailable_message(self.ground))

    def test_message_asks_to_check_a_domestic_address(self):
        order = self._order(self.cheap)
        message = order._int_shipping_unavailable_message(self.env["delivery.carrier"])
        self.assertIn("ZIP", message)

    def test_message_names_a_foreign_country(self):
        canada = self.env.ref("base.ca")
        partner = self.customer.copy({"country_id": canada.id, "state_id": False, "zip": "M5V 3L9"})
        order = self._order(self.cheap, partner)
        message = order._int_shipping_unavailable_message(self.env["delivery.carrier"])
        self.assertIn(canada.name, message)

    def test_checkout_delivery_form_shows_the_message(self):
        order = self._order(self.cheap)
        html = str(self.env["ir.ui.view"]._render_template("website_sale.delivery_form", {
            "delivery_methods": self.env["delivery.carrier"],
            "selected_dm_id": False,
            "order": order,
        }))
        self.assertIn("o_int_shipping_unavailable", html)
        self.assertIn("ZIP code", html)
        self.assertIn('href="/contactus"', html)

    def _pickup(self):
        if "in_store" not in dict(self.env["delivery.carrier"]._fields["delivery_type"].selection):
            self.skipTest("website_sale_collect is not installed")
        return self.env["delivery.carrier"].create({
            "name": "Pick up in store",
            "delivery_type": "in_store",
            "product_id": self.ground.product_id.id,
            "sequence": 1,
        })

    def test_new_cart_defaults_to_shipping_not_store_pickup(self):
        pickup = self._pickup()
        order = self._order(self.cheap)
        available = pickup | self.ground | self.two_day
        self.assertEqual(order._get_preferred_delivery_method(available), self.ground)
        self.assertEqual(order._get_preferred_delivery_method(pickup), pickup)

    def test_pickup_checkout_fell_back_to_gives_way_to_shipping(self):
        pickup = self._pickup()
        order = self._order(self.cheap)
        order._set_delivery_method(pickup)
        self.assertEqual(order._get_preferred_delivery_method(pickup | self.ground), self.ground)
        order._int_drop_unchosen_pickup()
        self.assertFalse(order.carrier_id)

    def test_pickup_the_customer_chose_is_kept(self):
        pickup = self._pickup()
        order = self._order(self.cheap)
        order._set_delivery_method(pickup)
        order.int_chosen_carrier_id = pickup
        self.assertEqual(order._get_preferred_delivery_method(pickup | self.ground), pickup)
        order._int_drop_unchosen_pickup()
        self.assertEqual(order.carrier_id, pickup)

    def _set_delivery_method_as_customer(self, order, carrier):
        website = self.env["website"].search([], limit=1)
        order.website_id = website
        with MockRequest(self.env, website=website, sale_order_id=order.id) as request:
            request.cart = order
            # Odoo only completes an override's routing when it builds the live routing
            # map, so call the undecorated method.
            IntShippoDelivery.shop_set_delivery_method.original_endpoint(
                IntShippoDelivery(), dm_id=carrier.id,
            )

    def test_clicking_a_different_method_records_the_choice(self):
        pickup = self._pickup()
        order = self._order(self.cheap)
        order._set_delivery_method(self.ground)
        self._set_delivery_method_as_customer(order, pickup)
        self.assertEqual(order.carrier_id, pickup)
        self.assertEqual(order.int_chosen_carrier_id, pickup)

    def test_page_load_resending_the_current_method_is_not_a_choice(self):
        pickup = self._pickup()
        order = self._order(self.cheap)
        order._set_delivery_method(pickup)
        self._set_delivery_method_as_customer(order, pickup)
        self.assertFalse(order.int_chosen_carrier_id)

    def test_label_purchase_names_the_contact_missing_a_phone(self):
        no_phone = self.customer.copy({"name": "No Phone Customer", "phone": False})
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.out_type_id.id,
            "partner_id": no_phone.id,
            "location_id": self.warehouse.lot_stock_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
        })
        with self.assertRaisesRegex(UserError, "No Phone Customer"):
            picking._int_shippo_check_label_phones()
