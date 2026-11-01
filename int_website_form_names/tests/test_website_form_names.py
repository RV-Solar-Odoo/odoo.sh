import json

from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestWebsiteFormNames(HttpCase):

    def _submit(self, **fields):
        response = self.url_open("/website/form/crm.lead", data={"name": "Dealer inquiry", **fields})
        return json.loads(response.content)

    def test_names_combine_and_stay_out_of_the_description(self):
        result = self._submit(**{"First Name": " Sam ", "Last Name": "Rivera"})
        lead = self.env["crm.lead"].browse(result["id"])
        self.assertEqual(lead.contact_name, "Sam Rivera")
        self.assertNotIn("Rivera", lead.description or "")

    def test_blank_last_name_is_refused(self):
        before = self.env["crm.lead"].search_count([])
        result = self._submit(**{"First Name": "Sam", "Last Name": "  "})
        self.assertIn("error", result)
        self.assertEqual(self.env["crm.lead"].search_count([]), before)

    def test_form_without_the_fields_is_untouched(self):
        result = self._submit(contact_name="Sam Rivera")
        self.assertEqual(self.env["crm.lead"].browse(result["id"]).contact_name, "Sam Rivera")
