from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalSalesRep(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

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
