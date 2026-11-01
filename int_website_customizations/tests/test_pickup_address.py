from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestPickupAddressName(TransactionCase):

    def test_store_pickup_drops_the_checkout_placeholder(self):
        customer = self.env["res.partner"].create({"name": "Annie King"})
        placeholder = self.env["res.partner"].create({
            "name": "Anonymous express checkout partner for order S00671",
            "type": "delivery",
            "parent_id": customer.id,
        })
        pickup = self.env["res.partner"].create({
            "name": "RVSB",
            "type": "delivery",
            "parent_id": placeholder.id,
            "is_pickup_location": True,
            "street": "335 Commerce St",
            "city": "Hurricane",
            "zip": "84737",
        })

        self.assertEqual(pickup.display_name, "In-Store Pickup, RVSB")
        shown = pickup.with_context(show_address=True).display_name
        self.assertEqual(shown.split("\n")[0], "In-Store Pickup, RVSB")
        self.assertIn("335 Commerce St", shown)
        self.assertEqual(placeholder.display_name, "Annie King, Anonymous express checkout partner for order S00671")

    def test_store_pickup_ignores_a_company_name(self):
        company = self.env["res.partner"].create({"name": "Annie Co", "is_company": True})
        pickup = self.env["res.partner"].create({
            "name": "RVSB",
            "type": "delivery",
            "parent_id": company.id,
            "is_pickup_location": True,
            "street": "335 Commerce St",
        })
        self.assertEqual(pickup.display_name, "In-Store Pickup, RVSB")

    def test_a_pickup_flag_without_an_address_keeps_the_customer_name(self):
        customer = self.env["res.partner"].create({"name": "Annie King"})
        label = self.env["res.partner"].create({
            "name": "In-Store Pickup",
            "type": "delivery",
            "parent_id": customer.id,
            "is_pickup_location": True,
        })
        self.assertEqual(label.display_name, "Annie King, In-Store Pickup")

    def test_a_normal_delivery_address_keeps_the_customer_name(self):
        customer = self.env["res.partner"].create({"name": "Annie King"})
        delivery = self.env["res.partner"].create({
            "name": "Warehouse",
            "type": "delivery",
            "parent_id": customer.id,
        })
        self.assertEqual(delivery.display_name, "Annie King, Warehouse")
