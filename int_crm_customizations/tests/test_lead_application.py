from odoo.tests import TransactionCase, tagged

from odoo.addons.int_crm_customizations.models.lead_application import APPLICATION_FORM_FIELDS


@tagged("post_install", "-at_install")
class TestLeadApplication(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us = cls.env.ref("base.us")
        States = cls.env["res.country.state"]
        cls.texas = States.search([("country_id", "=", cls.us.id), ("code", "=", "TX")])
        cls.ohio = States.search([("country_id", "=", cls.us.id), ("code", "=", "OH")])
        cls.company = cls.env.company
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Application Dealer",
            "company_id": cls.company.id,
            "currency_id": cls.company.currency_id.id,
        })

    def _lead(self, email, **values):
        return self.env["crm.lead"].create({
            "name": "Dealer application",
            "contact_name": "Sam Applicant",
            "partner_name": "Sunny RV Co",
            "email_from": email,
            "type": "opportunity",
            "company_id": self.company.id,
            "street": "1 Main St",
            "city": "Austin",
            "zip": "78701",
            "state_id": self.texas.id,
            "country_id": self.us.id,
            **values,
        })

    def _billing(self):
        return {
            "int_billing_different": True,
            "int_billing_street": "PO Box 9",
            "int_billing_city": "Columbus",
            "int_billing_state_id": self.ohio.id,
            "int_billing_zip": "43004",
            "int_billing_country_id": self.us.id,
        }

    def test_application_fields_are_offered_to_the_website_editor(self):
        writable = self.env["ir.model"]._get("crm.lead")._get_form_writable_fields()
        for name in APPLICATION_FORM_FIELDS:
            self.assertIn(name, writable)
        # State is matched from the typed box, never posted as an id.
        self.assertNotIn("state_id", writable)

    def test_typed_state_is_matched_by_code_or_name(self):
        Lead = self.env["crm.lead"]
        values = Lead._int_application_values({"street": "1 Main St", "int_state_text": " tx "})
        self.assertEqual(values["state_id"], self.texas.id)
        self.assertEqual(values["country_id"], self.us.id)
        self.assertNotIn("int_state_text", values)
        values = Lead._int_application_values({"city": "Austin", "int_state_text": "Texas"})
        self.assertEqual(values["state_id"], self.texas.id)
        # No match: the text stays on the lead for staff.
        values = Lead._int_application_values({"city": "Austin", "int_state_text": "Atlantis"})
        self.assertNotIn("state_id", values)
        self.assertEqual(values["int_state_text"], "Atlantis")

    def test_unticked_billing_box_drops_the_billing_fields(self):
        values = self.env["crm.lead"]._int_application_values({
            "street": "1 Main St",
            "int_billing_street": "PO Box 9",
            "int_billing_state_text": "OH",
            "int_facebook": "  sunnyrv  ",
            "int_tiktok": "   ",
        })
        self.assertFalse([name for name in values if name.startswith("int_billing")])
        self.assertEqual(values["int_facebook"], "sunnyrv")
        self.assertFalse(values["int_tiktok"])

    def test_ticked_billing_box_matches_the_billing_state_and_country(self):
        values = self.env["crm.lead"]._int_application_values({
            "street": "1 Main St",
            "int_billing_different": True,
            "int_billing_street": "PO Box 9",
            "int_billing_state_text": "oh",
        })
        self.assertEqual(values["int_billing_state_id"], self.ohio.id)
        self.assertEqual(values["int_billing_country_id"], self.us.id)

    def test_conversion_puts_the_billing_address_under_the_company(self):
        lead = self._lead("convert-app@example.com", int_instagram="@sunnyrv", **self._billing())
        lead._handle_partner_assignment(create_missing=True)
        company = lead.partner_id.commercial_partner_id
        self.assertEqual(company.name, "Sunny RV Co")
        self.assertEqual((company.street, company.state_id), ("1 Main St", self.texas))
        billing = company.child_ids.filtered(lambda child: child.type == "invoice")
        self.assertEqual(len(billing), 1)
        self.assertEqual((billing.street, billing.city, billing.state_id), ("PO Box 9", "Columbus", self.ohio))
        # Social links stay on the lead only.
        self.assertNotIn("int_instagram", company._fields)

    def test_create_dealer_account_makes_the_company_with_its_addresses(self):
        lead = self._lead("invite-app@example.com", **self._billing())
        action = lead.action_int_open_dealer_invite()
        self.env["int.dealer.invite"].with_context(**action["context"]).create({
            "pricelist_id": self.pricelist.id,
        }).action_confirm()
        person = lead.partner_id
        company = person.commercial_partner_id
        self.assertNotEqual(person, company)
        self.assertEqual(person.name, "Sam Applicant")
        self.assertEqual(company.street, "1 Main St")
        self.assertEqual(company.company_id, self.company)
        billing = company.child_ids.filtered(lambda child: child.type == "invoice")
        self.assertEqual(billing.street, "PO Box 9")
        # Running it again doesn't add a second billing address.
        action = lead.action_int_open_dealer_invite()
        self.env["int.dealer.invite"].with_context(**action["context"]).create({
            "pricelist_id": self.pricelist.id,
        }).action_confirm()
        self.assertEqual(len(company.child_ids.filtered(lambda child: child.type == "invoice")), 1)

    def test_an_existing_address_is_not_overwritten_and_the_lead_keeps_what_was_typed(self):
        existing = self.env["res.partner"].create({
            "name": "Existing Dealer",
            "email": "existing-app@example.com",
            "street": "50 Old Rd",
            "city": "Dallas",
        })
        lead = self._lead("existing-app@example.com")
        lead.action_int_send_dealer_account_email()
        self.assertEqual(lead.partner_id, existing)
        self.assertEqual(existing.street, "50 Old Rd")
        self.assertEqual(lead.street, "1 Main St")

    def test_an_empty_contact_gets_the_application_address(self):
        existing = self.env["res.partner"].create({
            "name": "Checkout Only",
            "email": "empty-app@example.com",
        })
        lead = self._lead("empty-app@example.com")
        lead.action_int_send_dealer_account_email()
        self.assertEqual(lead.partner_id, existing)
        self.assertEqual((existing.street, existing.city, existing.state_id), ("1 Main St", "Austin", self.texas))
