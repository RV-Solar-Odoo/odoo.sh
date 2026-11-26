from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.int_sale_customizations.controllers.quote import PUBLIC_PRODUCT_KEYS
from odoo.addons.int_sale_customizations.models.dealer_quote import CUSTOMER_PRICE_KEYS


@tagged("post_install", "-at_install")
class TestDealerQuotes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Quote = cls.env["int.dealer.quote"]
        cls.battery = cls._product("Customer Quote Battery", 200, 150, "INT-QTE-BAT")
        cls.cable = cls._product("Customer Quote Cable", 40, 30, "INT-QTE-CBL")
        cls.bare = cls._product("Customer Quote Bare", 80, 0, "INT-QTE-BARE")
        cls.hidden = cls._product("Customer Quote Hidden", 10, 10, "INT-QTE-HIDDEN", published=False)
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Customer Quote Wholesale",
            "currency_id": cls.company.currency_id.id,
            "item_ids": [Command.create({
                "applied_on": "3_global",
                "compute_price": "percentage",
                "percent_price": 50,
            })],
        })
        cls.dealer = cls.env["res.partner"].create({"name": "Quote Dealer", "is_company": True})
        cls.other = cls.env["res.partner"].create({"name": "Other Quote Dealer", "is_company": True})
        dealer = cls.dealer.with_company(cls.company).sudo()
        values = {"property_product_pricelist": cls.pricelist.id}
        if "specific_property_product_pricelist" in dealer._fields:
            values["specific_property_product_pricelist"] = cls.pricelist.id
        dealer.write(values)
        cls.owner = cls._portal(cls.dealer, "quote-owner@example.com", "owner")
        cls.buyer = cls._portal(
            cls.env["res.partner"].create({"name": "Quote Buyer", "parent_id": cls.dealer.id}),
            "quote-buyer@example.com", "buyer",
        )
        cls.viewer = cls._portal(
            cls.env["res.partner"].create({"name": "Quote Viewer", "parent_id": cls.dealer.id}),
            "quote-viewer@example.com", "viewer",
        )
        cls.stranger = cls._portal(cls.other, "quote-stranger@example.com", "owner")

    @classmethod
    def _product(cls, name, price, map_price, code, published=True):
        template = cls.env["product.template"].create({
            "name": name,
            "type": "consu",
            "list_price": price,
            "map_price": map_price,
            "sale_ok": True,
            "taxes_id": [Command.clear()],
        })
        if "is_published" in template._fields:
            template.is_published = published
        if "website_published" in template._fields:
            template.website_published = published
        template.product_variant_id.default_code = code
        return template.product_variant_id

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

    def _quote(self, user=None, customer="Pat Retail"):
        return self.Quote.with_user(user or self.buyer)._int_create(
            user or self.buyer, self.company, customer, email="pat@example.com", phone="555",
        )

    def test_a_new_quote_belongs_to_the_dealer_and_starts_at_map(self):
        with self.assertRaises(UserError):
            self.Quote._int_create(self.viewer, self.company, "Nope")
        quote = self._quote()
        self.assertEqual(quote.name, "Q0001")
        self.assertEqual(quote.partner_id, self.dealer)
        self.assertEqual(quote.company_id, self.company)
        self.assertEqual(quote.price_basis, "map")
        self.assertEqual(quote.customer_email, "pat@example.com")
        self.assertTrue(quote.valid_until)
        again = self._quote(customer="Second")
        self.assertEqual(again.name, "Q0002")

    def test_search_price_is_the_customer_price_and_not_wholesale(self):
        self.assertEqual(PUBLIC_PRODUCT_KEYS, CUSTOMER_PRICE_KEYS)
        self.assertFalse(set(PUBLIC_PRODUCT_KEYS) & {"cost", "dealer_cost", "wholesale"})
        quote = self._quote()
        choice = quote._int_product_choice(self.battery)
        self.assertEqual(set(choice), set(CUSTOMER_PRICE_KEYS))
        self.assertEqual(choice["price"], 150.0)
        self.assertFalse(choice["map_missing"])
        self.assertEqual(choice["sku"], "INT-QTE-BAT")
        self.assertAlmostEqual(quote._int_wholesale(self.battery, 1), 100.0)
        self.assertNotEqual(choice["price"], quote._int_wholesale(self.battery, 1))
        found = self.Quote._int_find_products(self.company, "INT-QTE-BAT")
        self.assertIn(self.battery, found)
        self.assertFalse(self.Quote._int_find_products(self.company, "INT-QTE-HIDDEN"))

    def test_a_product_without_map_uses_msrp(self):
        quote = self._quote()
        quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.bare.id)})
        line = quote.line_ids
        self.assertEqual(line.unit_price, 80.0)
        self.assertTrue(line.map_missing)
        self.assertFalse(line.below_map)
        self.assertFalse(line.price_manual)
        choice = quote._int_product_choice(self.bare)
        self.assertEqual(choice["price"], 80.0)
        self.assertTrue(choice["map_missing"])

    def test_a_typed_price_below_map_stays_when_the_basis_changes(self):
        quote = self._quote()
        quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.battery.id)})
        quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.cable.id)})
        battery = quote.line_ids.filtered(lambda line: line.product_id == self.battery)
        cable = quote.line_ids.filtered(lambda line: line.product_id == self.cable)
        self.assertEqual(battery.unit_price, 150.0)
        self.assertEqual(cable.unit_price, 30.0)
        self.assertEqual(battery._int_margin_label(), "33%")
        quote._int_apply(self.buyer, {
            "price_basis": "msrp",
            "qty_%s" % battery.id: "1",
            "price_%s" % battery.id: "120",
            "qty_%s" % cable.id: "2",
            "price_%s" % cable.id: "30",
        })
        self.assertEqual(quote.price_basis, "msrp")
        self.assertEqual(battery.unit_price, 120.0)
        self.assertTrue(battery.price_manual)
        self.assertTrue(battery.below_map)
        self.assertEqual(cable.quantity, 2.0)
        self.assertEqual(cable.unit_price, 40.0)
        self.assertFalse(cable.price_manual)
        self.assertFalse(cable.below_map)
        self.assertAlmostEqual(battery.dealer_cost, 100.0)
        self.assertAlmostEqual(quote.margin_amount, 60.0)
        quote._int_apply(self.buyer, {"qty_%s" % battery.id: "0"})
        self.assertFalse(quote.line_ids.filtered(lambda line: line.product_id == self.battery))

    def test_a_custom_line_has_no_wholesale(self):
        quote = self._quote()
        quote._int_apply(self.buyer, {
            "intent": "custom",
            "custom_description": "Install the inverter",
            "custom_quantity": "2",
            "custom_price": "75",
            "notes": "Call first",
            "customer_name": "Pat Retail",
        })
        line = quote.line_ids
        self.assertEqual(line.line_type, "custom")
        self.assertFalse(line.product_id)
        self.assertEqual(line.dealer_cost, 0.0)
        self.assertFalse(line.below_map)
        self.assertEqual(line.price_subtotal, 150.0)
        self.assertEqual(quote.notes, "Call first")
        self.assertEqual(quote.margin_amount, 0.0)
        with self.assertRaises(UserError):
            quote._int_apply(self.buyer, {"intent": "custom", "custom_description": "  "})

    def test_only_the_owner_changes_the_company_default(self):
        first = self._quote()
        self.assertEqual(first.price_basis, "map")
        with self.assertRaises(UserError):
            self.env["res.partner"]._int_set_quote_basis(self.buyer, "msrp")
        with self.assertRaises(AccessError):
            self.dealer.with_user(self.owner).write({"int_quote_price_basis": "msrp"})
        with self.assertRaises(AccessError):
            self.dealer.with_user(self.stranger).write({"int_quote_price_basis": "msrp"})
        self.env["res.partner"]._int_set_quote_basis(self.owner, "msrp")
        self.assertEqual(self.dealer.int_quote_price_basis, "msrp")
        self.assertEqual(first.price_basis, "map")
        second = self._quote(self.owner, "Next job")
        self.assertEqual(second.price_basis, "msrp")
        second._int_apply(self.owner, {"add_product": "1", "product_id": str(self.battery.id)})
        self.assertEqual(second.line_ids.unit_price, 200.0)

    def test_another_dealer_cannot_see_or_change_the_quote(self):
        quote = self._quote()
        self.assertFalse(self.Quote._int_for_user(self.stranger, self.company, quote.id))
        self.assertFalse(self.Quote._int_for_user(self.viewer, self.company, quote.id))
        self.assertEqual(self.Quote._int_for_user(self.buyer, self.company, quote.id), quote)
        with self.assertRaises(AccessError):
            self.Quote.with_user(self.viewer).search([("id", "=", quote.id)])
        with self.assertRaises(AccessError):
            self.Quote.with_user(self.stranger).search([("id", "=", quote.id)])
        with self.assertRaises(UserError):
            quote._int_apply(self.stranger, {"customer_name": "Stolen", "notes": "nope"})
        self.assertEqual(quote.customer_name, "Pat Retail")

    def test_the_address_has_to_be_one_of_the_dealers_customers(self):
        quote = self._quote()
        address = self.env["res.partner"].create({
            "name": "Pat Shop",
            "parent_id": self.dealer.id,
            "type": "delivery",
            "int_address_category": "customer",
        })
        other = self.env["res.partner"].create({
            "name": "Not Theirs",
            "parent_id": self.other.id,
            "type": "delivery",
            "int_address_category": "customer",
        })
        quote._int_apply(self.buyer, {"customer_address_id": str(address.id), "customer_name": "Pat Retail"})
        self.assertEqual(quote.customer_address_id, address)
        quote._int_apply(self.buyer, {"customer_address_id": str(other.id), "customer_name": "Pat Retail"})
        self.assertFalse(quote.customer_address_id)
        with self.assertRaises(UserError):
            quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.hidden.id)})
