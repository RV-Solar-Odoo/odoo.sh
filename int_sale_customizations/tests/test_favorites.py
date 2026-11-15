from lxml import etree

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFavoriteOrders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.int_max_favorites = 25
        cls.Favorite = cls.env["int.favorite.order"]
        cls.battery = cls._product("Favorite battery", "consu", 100, "INT-FAV-BAT")
        cls.cable = cls._product("Favorite cable", "consu", 10, "INT-FAV-CBL")
        cls.shunt = cls._product("Favorite shunt", "consu", 50, "INT-FAV-SHT")
        cls.shipping = cls._product("Favorite shipping", "service", 0, "")
        cls.dealer = cls.env["res.partner"].create({"name": "Favorite Dealer", "is_company": True})
        cls.other_dealer = cls.env["res.partner"].create({"name": "Other Favorite Dealer", "is_company": True})
        cls.owner = cls._portal(cls.dealer, "fav-owner@example.com", "owner")
        cls.buyer = cls._portal(
            cls.env["res.partner"].create({"name": "Favorite Buyer", "parent_id": cls.dealer.id}),
            "fav-buyer@example.com", "buyer",
        )
        cls.viewer = cls._portal(
            cls.env["res.partner"].create({"name": "Favorite Viewer", "parent_id": cls.dealer.id}),
            "fav-viewer@example.com", "viewer",
        )
        cls.stranger = cls._portal(cls.other_dealer, "fav-stranger@example.com", "owner")
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.dealer.id,
            "order_line": [
                Command.create({"product_id": cls.battery.id, "product_uom_qty": 2}),
                Command.create({"product_id": cls.cable.id, "product_uom_qty": 3}),
                Command.create({"product_id": cls.shipping.id, "name": "Ground", "price_unit": 12, "is_delivery": True}),
                Command.create({"display_type": "line_note", "name": "Leave at the dock"}),
            ],
        })
        cls.order.action_confirm()

    @classmethod
    def _product(cls, name, kind, price, code):
        product = cls.env["product.product"].create({
            "name": name, "type": kind, "list_price": price, "default_code": code or False, "sale_ok": True,
        })
        if "is_published" in product.product_tmpl_id._fields:
            product.product_tmpl_id.is_published = True
        return product

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

    def _save(self, user, order=None, name=None):
        return self.Favorite.with_user(user)._int_create_from_order(user, self.company, order or self.order, name=name)

    def test_saving_an_order_copies_products_only_and_names_it_by_order_number(self):
        favorite = self._save(self.buyer)
        self.assertEqual(favorite.name, self.order.name)
        self.assertEqual(favorite.source_order_id, self.order)
        self.assertEqual(favorite.partner_id, self.dealer)
        self.assertEqual(favorite.line_ids.product_id, self.battery | self.cable)
        self.assertEqual(sorted(favorite.line_ids.mapped("quantity")), [2.0, 3.0])
        self.assertEqual(favorite.item_count, 5.0)
        named = self.Favorite._int_clean_name("  Standard   12V van kit ", "x")
        self.assertEqual(named, "Standard 12V van kit")

    def test_favorites_are_shared_by_the_dealer_and_saved_once_per_order(self):
        favorite = self._save(self.buyer, name="Van kit")
        self.assertEqual(self.Favorite._int_for_user(self.owner, self.company), favorite)
        self.assertEqual(self.Favorite._int_for_user(self.viewer, self.company), favorite)
        self.assertFalse(self.Favorite._int_for_user(self.stranger, self.company))
        self.assertEqual(self._save(self.owner), favorite)
        self.assertEqual(self.Favorite._int_by_order(self.owner, self.company, self.order), {self.order.id: favorite})
        with self.assertRaises(UserError):
            self._save(self.stranger)

    def test_viewer_and_accountant_cannot_change_favorites(self):
        with self.assertRaises(UserError):
            self._save(self.viewer)
        favorite = self._save(self.owner)
        with self.assertRaises(UserError):
            favorite._int_apply_edit(self.viewer, name="Nope")
        with self.assertRaises(UserError):
            favorite._int_archive(self.viewer)

    def test_limit_counts_active_favorites_and_restore_checks_it(self):
        self.company.int_max_favorites = 1
        first = self._save(self.owner)
        second_order = self.order.copy()
        second_order.action_confirm()
        with self.assertRaises(UserError):
            self._save(self.owner, second_order)
        first._int_archive(self.owner)
        self.assertFalse(self.Favorite._int_for_user(self.owner, self.company))
        second = self._save(self.owner, second_order)
        with self.assertRaises(UserError):
            first._int_restore(self.owner, self.company)
        second._int_archive(self.owner)
        first._int_restore(self.owner, self.company)
        self.assertTrue(first.active)

    def test_edit_renames_changes_quantities_removes_and_adds(self):
        favorite = self._save(self.owner)
        battery_line = favorite.line_ids.filtered(lambda line: line.product_id == self.battery)
        cable_line = favorite.line_ids.filtered(lambda line: line.product_id == self.cable)
        hidden = self._product("Favorite hidden", "consu", 1, "INT-FAV-HID")
        hidden.active = False
        favorite._int_apply_edit(
            self.owner,
            name="Standard 12V van kit",
            quantities={battery_line.id: "4", cable_line.id: "abc"},
            removed={cable_line.id},
            added={self.shunt.id: "2", hidden.id: "1", self.battery.id: "1"},
        )
        self.assertEqual(favorite.name, "Standard 12V van kit")
        self.assertEqual(favorite.line_ids.product_id, self.battery | self.shunt)
        self.assertEqual(battery_line.quantity, 5.0)
        self.assertEqual(favorite.line_ids.filtered(lambda line: line.product_id == self.shunt).quantity, 2.0)
        with self.assertRaises(UserError):
            favorite._int_apply_edit(self.owner, removed=set(favorite.line_ids.ids))

    def test_cart_plan_takes_the_ticked_lines_and_skips_unavailable_products(self):
        favorite = self._save(self.owner)
        battery_line = favorite.line_ids.filtered(lambda line: line.product_id == self.battery)
        cable_line = favorite.line_ids.filtered(lambda line: line.product_id == self.cable)
        addable, skipped = favorite._int_cart_plan(False)
        self.assertEqual(dict((product, qty) for product, qty in addable), {self.battery: 2.0, self.cable: 3.0})
        self.assertFalse(skipped)
        addable, _skipped = favorite._int_cart_plan(False, {battery_line.id: "6"})
        self.assertEqual(addable, [(self.battery, 6.0)])
        self.cable.active = False
        addable, skipped = favorite._int_cart_plan(False, {battery_line.id: "1", cable_line.id: "1"})
        self.assertEqual(addable, [(self.battery, 1.0)])
        self.assertEqual(len(skipped), 1)

    def test_saving_a_cart(self):
        cart = self.env["sale.order"].create({
            "partner_id": self.buyer.partner_id.id,
            "order_line": [
                Command.create({"product_id": self.shunt.id, "product_uom_qty": 2}),
                Command.create({"product_id": self.shunt.id, "product_uom_qty": 1}),
                Command.create({"product_id": self.shipping.id, "name": "Ground", "price_unit": 12, "is_delivery": True}),
            ],
        })
        favorite = self.Favorite._int_create_from_cart(self.buyer, self.company, cart, name="Shop stock")
        self.assertEqual(favorite.name, "Shop stock")
        self.assertFalse(favorite.source_order_id)
        self.assertEqual(favorite.partner_id, self.dealer)
        self.assertEqual(favorite.line_ids.product_id, self.shunt)
        self.assertEqual(favorite.line_ids.filtered(lambda line: line.product_id == self.shunt).quantity, 3.0)
        with self.assertRaises(UserError):
            self.Favorite._int_create_from_cart(self.stranger, self.company, cart, name="Not mine")
        self.assertIn("Saved cart", self.Favorite._int_clean_name("", "Saved cart 2026-11-15"))

    def test_notice_reads_only_this_dealers_favorites(self):
        favorite = self._save(self.owner)
        notice = self.Favorite._int_notice(self.buyer, self.company, {"int_fav_saved": str(favorite.id)})
        self.assertEqual(notice["kind"], "saved")
        self.assertEqual(notice["favorite"], favorite)
        self.assertFalse(self.Favorite._int_notice(self.stranger, self.company, {"int_fav_saved": str(favorite.id)}))
        favorite._int_archive(self.owner)
        notice = self.Favorite._int_notice(self.buyer, self.company, {"int_fav_removed": str(favorite.id)})
        self.assertEqual(notice["kind"], "removed")

    def test_tabs_and_button_labels(self):
        html = str(self.env["ir.qweb"]._render("int_sale_customizations.portal_order_tabs", {
            "int_tab": "favorites",
            "int_tab_counts": {"all": 4, "favorites": 2, "backorders": 1, "quotes": 0},
        }))
        for href in ("/my/orders", "/my/favorites", "/my/backorders", "/my/quotes"):
            self.assertIn(f'href="{href}"', html)
        self.assertEqual(html.count('aria-current="page"'), 1)
        self.assertIn("Favorite Orders", html)
        arch = self.env.ref("int_sale_customizations.portal_my_favorites").arch
        for label in ("Add Selected to Cart", "Edit Favorite", "View Original Order"):
            self.assertIn(label, arch)
        edit = self.env.ref("int_sale_customizations.portal_favorite_edit").arch
        for label in ("Save Changes", "Delete This Favorite"):
            self.assertIn(label, edit)
        self.assertIn("Save Cart as a Favorite", self.env.ref("int_sale_customizations.cart_save_favorite").arch)
        # The Quotations box is off My Portal; quotes are a tab now.
        home = etree.fromstring(self.env.ref("portal.portal_my_home").get_combined_arch())
        quote_entries = home.xpath("//t[@t-call='portal.portal_docs_entry'][t[@t-set='url' and @t-value=\"'/my/quotes'\"]]")
        self.assertTrue(quote_entries)
        self.assertTrue(all(entry.get("t-if") == "False" for entry in quote_entries))
