import base64

from odoo import Command, http
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.int_sale_customizations.controllers.quote import PUBLIC_PRODUCT_KEYS
from odoo.addons.int_sale_customizations.models.dealer_quote import CUSTOMER_PRICE_KEYS
from odoo.addons.int_sale_customizations.models.res_partner import int_readable_accent

# A 1x1 transparent PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


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

    def test_prices_swapped_on_the_page_by_a_basis_switch_stay_automatic(self):
        # The editor swaps the prices live when MAP/MSRP is switched, then posts them.
        quote = self._quote()
        quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.cable.id)})
        cable = quote.line_ids
        quote._int_apply(self.buyer, {"price_basis": "msrp", "price_%s" % cable.id: "40"})
        self.assertEqual(cable.unit_price, 40.0)
        self.assertFalse(cable.price_manual)
        quote._int_apply(self.buyer, {"price_basis": "map", "price_%s" % cable.id: "30"})
        self.assertEqual(cable.unit_price, 30.0)
        self.assertFalse(cable.price_manual)
        # A typed price still sticks through a switch.
        quote._int_apply(self.buyer, {"price_%s" % cable.id: "33"})
        self.assertTrue(cable.price_manual)
        quote._int_apply(self.buyer, {"price_basis": "msrp", "price_%s" % cable.id: "33"})
        self.assertEqual(cable.unit_price, 33.0)
        self.assertTrue(cable.price_manual)

    def test_the_bin_posts_one_to_remove_and_zero_to_keep(self):
        quote = self._quote()
        quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.cable.id)})
        line = quote.line_ids
        quote._int_apply(self.buyer, {"remove_%s" % line.id: "0"})
        self.assertTrue(line.exists())
        quote._int_apply(self.buyer, {"remove_%s" % line.id: "1"})
        self.assertFalse(line.exists())

    def test_the_pdf_is_the_dealers_and_never_shows_wholesale_or_our_company(self):
        quote = self._quote()
        quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.battery.id)})
        line = quote.line_ids
        self.assertAlmostEqual(line.dealer_cost, 100.0)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "int_sale_customizations.action_report_int_dealer_quote", quote.ids,
        )[0].decode()
        self.assertIn("Quote Dealer", html)
        self.assertIn(quote.name, html)
        self.assertIn("Pat Retail", html)
        self.assertIn("INT-QTE-BAT", html)
        self.assertIn("150.00", html)
        # The dealer's cost and margin, and RV Solar's company, are not on it.
        self.assertNotIn("100.00", html)
        self.assertNotIn("Wholesale", html)
        self.assertNotIn("Margin", html)
        self.assertNotIn(self.company.name, html)
        self.assertEqual(quote._get_report_base_filename(), "Quote %s" % quote.name)

    def test_a_new_quote_can_start_at_msrp_without_changing_the_default(self):
        quote = self.Quote.with_user(self.buyer)._int_create(self.buyer, self.company, "Walk-in", basis="msrp")
        self.assertEqual(quote.price_basis, "msrp")
        self.assertEqual(self.dealer.int_quote_price_basis, "map")
        quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.battery.id)})
        self.assertEqual(quote.line_ids.unit_price, 200.0)

    def test_quote_settings_are_the_owners_and_check_the_colour(self):
        Partner = self.env["res.partner"]
        with self.assertRaises(UserError):
            Partner._int_set_quote_settings(self.buyer, {"quote_accent": "#1f7a4d"})
        with self.assertRaises(UserError):
            Partner._int_set_quote_settings(self.owner, {"quote_accent": "custom", "quote_accent_custom": "green"})
        with self.assertRaises(AccessError):
            self.dealer.with_user(self.owner).write({"int_quote_accent": "#1f7a4d"})
        Partner._int_set_quote_settings(self.owner, {
            "price_basis": "msrp",
            "quote_accent": "custom",
            "quote_accent_custom": "#1F7A4D",
            "quote_subheading": "  Solar   and batteries ",
            "quote_footer": "Thank you.",
        }, logo=("logo.png", PNG))
        self.assertEqual(self.dealer.int_quote_price_basis, "msrp")
        self.assertEqual(self.dealer.int_quote_accent, "#1f7a4d")
        self.assertEqual(self.dealer.int_quote_subheading, "Solar and batteries")
        self.assertEqual(self.dealer.int_quote_footer, "Thank you.")
        self.assertTrue(self.dealer.image_1920)
        # A colour too light to read as text is darkened for text only.
        self.assertEqual(int_readable_accent("#1f2433"), "#1f2433")
        light = int_readable_accent("#ffee00")
        self.assertNotEqual(light, "#ffee00")

    def test_the_pdf_prints_the_dealers_settings(self):
        self.env["res.partner"]._int_set_quote_settings(self.owner, {
            "quote_accent": "#c2410c",
            "quote_subheading": "Solar and batteries",
            "quote_footer": "Licence 12345. Thank you.",
        })
        quote = self._quote()
        quote._int_apply(self.buyer, {"add_product": "1", "product_id": str(self.battery.id)})
        quote._int_add_custom("Install", 1, 50)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "int_sale_customizations.action_report_int_dealer_quote", quote.ids,
        )[0].decode()
        self.assertIn("#c2410c", html)
        self.assertIn("Solar and batteries", html)
        self.assertIn("Licence 12345. Thank you.", html)
        self.assertIn("Prepared by", html)
        self.assertIn("Labor and charges", html)
        self.assertIn("150.00", html)
        self.assertNotIn("Wholesale", html)
        self.assertNotIn(self.company.name, html)


@tagged("post_install", "-at_install")
class TestDealerQuotePages(HttpCase):
    """The pages render for the roles that use them, so a template error fails the build."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("website.default_website").company_id
        cls.dealer = cls.env["res.partner"].create({"name": "Page Quote Dealer", "is_company": True})
        cls.owner = cls._portal("Page Owner", "page-quote-owner@example.com", "owner")
        cls.buyer = cls._portal("Page Buyer", "page-quote-buyer@example.com", "buyer")
        template = cls.env["product.template"].create({
            "name": "Page Quote Panel",
            "type": "consu",
            "list_price": 120,
            "map_price": 100,
            "sale_ok": True,
        })
        template.product_variant_id.default_code = "INT-PAGE-PNL"
        cls.quote = cls.env["int.dealer.quote"].with_user(cls.buyer)._int_create(
            cls.buyer, cls.company, "Robin Customer", email="robin@example.com",
        )
        cls.quote._int_add_product(template.product_variant_id)
        cls.quote._int_add_custom("Install", 1, 75)

    @classmethod
    def _portal(cls, name, login, role):
        partner = cls.env["res.partner"].create({"name": name, "parent_id": cls.dealer.id, "email": login})
        partner.sudo().write({"int_portal_role": role})
        return cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": name,
            "login": login,
            "password": login,
            "email": login,
            "partner_id": partner.id,
            "company_id": cls.company.id,
            "company_ids": [Command.set([cls.company.id])],
            "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
        })

    def test_editor_list_and_pdf_render_without_dealer_numbers_showing(self):
        self.authenticate(self.buyer.login, self.buyer.login)
        listing = self.url_open("/my/customer-quotes")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(self.quote.name, listing.text)
        self.assertNotIn('href="/my/customer-quotes/settings"', listing.text)
        editor = self.url_open("/my/customer-quotes/%s" % self.quote.id)
        self.assertEqual(editor.status_code, 200)
        self.assertIn("Show Dealer Info", editor.text)
        self.assertIn("o_int_dealer_only", editor.text)
        self.assertNotIn("o_int_show_dealer", editor.text)
        self.assertNotIn('name="price_basis"', editor.text)
        self.assertIn("Save Quote", editor.text)
        pdf = self.url_open("/my/customer-quotes/%s/pdf" % self.quote.id)
        self.assertEqual(pdf.status_code, 200)
        # Buyers don't get Quote Settings.
        settings = self.url_open("/my/customer-quotes/settings", allow_redirects=False)
        self.assertIn(settings.status_code, (302, 303))

    def test_owner_sees_and_saves_quote_settings(self):
        self.authenticate(self.owner.login, self.owner.login)
        page = self.url_open("/my/customer-quotes/settings")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Quote accent colour", page.text)
        self.assertIn('name="logo"', page.text)
        self.assertIn('name="quote_subheading"', page.text)
        saved = self.url_open("/my/customer-quotes/settings", data={
            "csrf_token": http.Request.csrf_token(self),
            "price_basis": "msrp",
            "quote_accent": "#0054a8",
            "quote_subheading": "Mobile power",
            "quote_footer": "Thanks!",
        }, files={"logo": ("logo.png", PNG, "image/png")})
        self.assertEqual(saved.status_code, 200)
        self.dealer.invalidate_recordset()
        self.assertEqual(self.dealer.int_quote_accent, "#0054a8")
        self.assertEqual(self.dealer.int_quote_subheading, "Mobile power")
        self.assertTrue(self.dealer.image_1920)
