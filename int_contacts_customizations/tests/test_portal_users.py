from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalUsers(TransactionCase):

    def _portal(self, partner, login):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name,
            "login": login,
            "email": login,
            "partner_id": partner.id,
            "company_id": self.env.company.id,
            "company_ids": [Command.set([self.env.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
        })

    def test_last_owner_cannot_be_removed(self):
        company = self.env["res.partner"].create({"name": "Owner Co", "is_company": True, "email": "owner-co@example.com"})
        owner = self._portal(company, "last-owner@example.com")
        with self.assertRaises(UserError):
            owner.int_portal_set_role("buyer", self.env.user)
        with self.assertRaises(UserError):
            owner.int_portal_set_active(False, self.env.user)
        self.assertEqual(owner.partner_id.int_portal_role or "owner", "owner")
        self.assertTrue(owner.active)

    def test_residential_clears_dock_and_forklift(self):
        partner = self.env["res.partner"].create({
            "name": "Site",
            "type": "delivery",
            "int_location_type": "commercial",
            "int_has_loading_dock": True,
            "int_has_forklift": True,
        })
        partner.write({"int_location_type": "residential", "int_has_loading_dock": True, "int_has_forklift": True})
        self.assertFalse(partner.int_has_loading_dock)
        self.assertFalse(partner.int_has_forklift)

    def test_company_address_stays_business(self):
        company = self.env["res.partner"].create({"name": "Business Co", "is_company": True})
        with self.assertRaises(UserError):
            company.write({"int_address_category": "customer"})

    def test_buyer_cannot_order_and_viewer_cannot_see_invoices_permission(self):
        company = self.env["res.partner"].create({"name": "Role Co", "is_company": True})
        buyer_partner = self.env["res.partner"].create({
            "name": "Buyer",
            "parent_id": company.id,
            "email": "role-buyer@example.com",
            "int_portal_role": "buyer",
        })
        buyer = self._portal(buyer_partner, "role-buyer@example.com")
        self.assertTrue(buyer.int_portal_can("place_orders"))
        self.assertFalse(buyer.int_portal_can("view_invoices"))
        self.assertTrue(buyer.int_portal_ordering_blocked() is False)
        viewer_partner = self.env["res.partner"].create({
            "name": "Viewer",
            "parent_id": company.id,
            "email": "role-viewer@example.com",
            "int_portal_role": "viewer",
        })
        viewer = self._portal(viewer_partner, "role-viewer@example.com")
        self.assertTrue(viewer.int_portal_ordering_blocked())
        self.assertFalse(viewer.int_portal_can("view_invoices"))
        self.assertFalse(viewer.int_portal_can("make_payments"))
        self.assertTrue(viewer.int_portal_can("view_orders"))

    def test_invite_refuses_another_companys_email(self):
        first = self.env["res.partner"].create({"name": "First Co", "is_company": True})
        other = self.env["res.partner"].create({"name": "Other Person", "email": "taken-portal@example.com"})
        self._portal(other, "taken-portal@example.com")
        with self.assertRaises(UserError):
            first.int_portal_invite_user("New", "taken-portal@example.com", "buyer")
