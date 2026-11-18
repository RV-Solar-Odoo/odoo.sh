import base64
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.int_crm_customizations.controllers.main import int_documents_from_form

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PDF_B64 = base64.b64encode(PDF)


@tagged("post_install", "-at_install")
class TestLeadDocuments(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Label = cls.env["int.lead.document.label"]
        cls.Document = cls.env["int.lead.document"]
        cls.license = cls.Label._int_by_code("business_license")
        cls.certificate = cls.Label._int_by_code("tax_certificate")
        cls.storefront = cls.Label._int_by_code("storefront")
        cls.other = cls.Label._int_by_code("other")
        cls.salesman = cls._user("doc-salesman@example.com", "sales_team.group_sale_salesman")
        cls.manager = cls._user("doc-manager@example.com", "sales_team.group_sale_manager")
        cls.lead = cls.env["crm.lead"].create({
            "name": "Dealer Application",
            "email_from": "dealer-docs@example.com",
            # Unassigned, so the salesman's Personal Leads rule lets them edit it.
            "user_id": False,
        })

    @classmethod
    def _user(cls, login, group):
        return cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": login.split("@")[0],
            "login": login,
            "email": login,
            "company_id": cls.env.company.id,
            "company_ids": [Command.set([cls.env.company.id])],
            "group_ids": [Command.set([cls.env.ref("base.group_user").id, cls.env.ref(group).id])],
        })

    def _upload(self, label, name="file.pdf", user=None, lead=None):
        Document = self.Document.with_user(user) if user else self.Document
        return Document.create({
            "lead_id": (lead or self.lead).id,
            "label_id": label.id,
            "upload": PDF_B64,
            "upload_name": name,
        })

    def test_starting_labels_exist_in_order(self):
        labels = self.license | self.certificate | self.storefront | self.other
        self.assertEqual(len(labels), 4)
        self.assertEqual(labels.sorted("sequence"), self.license | self.certificate | self.storefront | self.other)

    def test_form_uploads_are_labelled_by_their_field(self):
        attachments = self.env["ir.attachment"].create([
            {"name": name, "raw": PDF, "res_model": "crm.lead", "res_id": self.lead.id}
            for name in ("license.pdf", "front.jpg", "inside.jpg", "w9.pdf")
        ])
        int_documents_from_form(self.env, self.lead.id, [
            "Copy of Business License", "Business Storefront + Interior", "Business Storefront + Interior", "W-9 Form",
        ])
        documents = self.lead.int_document_ids
        by_file = {doc.attachment_id: doc.label_id for doc in documents}
        self.assertEqual(by_file[attachments[0]], self.license)
        self.assertEqual(by_file[attachments[1]], self.storefront)
        self.assertEqual(by_file[attachments[2]], self.storefront)
        self.assertEqual(by_file[attachments[3]].name, "W-9 Form")
        # Running it again does not file anything twice.
        int_documents_from_form(self.env, self.lead.id, ["Copy of Business License"])
        self.assertEqual(len(self.lead.int_document_ids), 4)

    def test_certificate_moves_to_documents_and_shows_in_files(self):
        lead = self.env["crm.lead"].create({
            "name": "Exempt Application",
            "x_is_tax_exempt": True,
            "x_tax_exemption_document": PDF_B64,
            "x_tax_exemption_document_filename": "resale.pdf",
        })
        self.assertFalse(lead.x_tax_exemption_document)
        self.assertEqual(lead.int_tax_certificate_id.label_id, self.certificate)
        self.assertEqual(lead.int_tax_certificate_id.name, "resale.pdf")
        self.assertEqual(lead.int_tax_certificate_status, "pending")
        attachment = lead.int_tax_certificate_id.attachment_id
        self.assertEqual((attachment.res_model, attachment.res_id), ("crm.lead", lead.id))
        self.assertFalse(attachment.res_field)
        files = self.env["ir.attachment"].search([("res_model", "=", "crm.lead"), ("res_id", "=", lead.id)])
        self.assertIn(attachment, files)

    def test_reviewed_records_who_and_when_and_logs_it(self):
        document = self._upload(self.license, user=self.salesman)
        document.with_user(self.salesman).write({"reviewed": True})
        self.assertEqual(document.reviewed_by_id, self.salesman)
        self.assertTrue(document.reviewed_on)
        self.assertIn(self.salesman.name, document.review_note)
        self.assertIn("as reviewed", self.lead.message_ids[:1].body)
        document.with_user(self.salesman).write({"reviewed": False})
        self.assertFalse(document.reviewed_by_id)
        self.assertFalse(document.review_note)

    def test_grant_needs_a_reviewed_certificate(self):
        lead = self.env["crm.lead"].create({
            "name": "Grant Application",
            "x_is_tax_exempt": True,
            "x_tax_exemption_reason": "resale",
        })
        with self.assertRaisesRegex(UserError, "Upload the Tax Exemption Certificate"):
            lead.action_grant_tax_exemption()
        certificate = self._upload(self.certificate, "resale.pdf", lead=lead)
        with self.assertRaisesRegex(UserError, "Review the Tax Exemption Certificate"):
            lead.action_grant_tax_exemption()
        certificate.reviewed = True
        self.assertEqual(lead.int_tax_certificate_status, "reviewed")
        partner = self.env["res.partner"].create({"name": "Grant Dealer", "is_company": True})
        lead.partner_id = partner
        with patch.object(type(lead), "_int_apply_tax_exemption", autospec=True) as apply:
            lead.action_grant_tax_exemption()
        self.assertTrue(lead.x_tax_exemption_approved)
        self.assertTrue(apply.called)

    def test_only_managers_delete_from_the_tab_or_files(self):
        document = self._upload(self.license, user=self.salesman)
        attachment = document.attachment_id
        with self.assertRaises(AccessError):
            document.with_user(self.salesman).unlink()
        with self.assertRaises(AccessError):
            attachment.with_user(self.salesman).unlink()
        document.with_user(self.manager).unlink()
        self.assertFalse(document.exists())
        self.assertFalse(attachment.exists())
        self.assertIn("deleted", self.lead.message_ids[:1].body)

    def test_change_label_is_logged(self):
        document = self._upload(self.other, "license.pdf", user=self.salesman)
        document.with_user(self.salesman).label_id = self.license
        self.assertEqual(document.label_id, self.license)
        self.assertIn("moved", self.lead.message_ids[:1].body)

    def test_reviewed_documents_copy_to_the_contact_once(self):
        partner = self.env["res.partner"].create({"name": "Copy Dealer", "is_company": True})
        reviewed = self._upload(self.license, "license.pdf")
        reviewed.reviewed = True
        pending = self._upload(self.storefront, "front.pdf")
        copied = self.lead._int_copy_documents_to_partner(partner)
        self.assertEqual(copied, reviewed)
        copy = reviewed.partner_attachment_id
        self.assertEqual((copy.res_model, copy.res_id), ("res.partner", partner.id))
        self.assertEqual(copy.name, "Copy of Business License – license.pdf")
        self.assertEqual(copy.raw, PDF)
        self.assertIn("not reviewed", self.lead.message_ids[:1].body)
        self.assertFalse(pending.partner_attachment_id)
        self.assertFalse(self.lead._int_copy_documents_to_partner(partner))
        # Copy to Contact on one file reviewed later.
        pending.reviewed = True
        self.lead.partner_id = partner
        pending.action_int_copy_to_contact()
        self.assertTrue(pending.partner_attachment_id)

    def test_approved_exemption_copies_the_certificate_file(self):
        partner = self.env["res.partner"].create({"name": "Exempt Dealer", "is_company": True})
        lead = self.env["crm.lead"].create({
            "name": "Approved Application",
            "partner_id": partner.id,
            "x_is_tax_exempt": True,
            "x_tax_exemption_reason": "resale",
        })
        certificate = self._upload(self.certificate, "resale.pdf", lead=lead)
        certificate.reviewed = True
        self.env["account.fiscal.position"].create({"name": "Wholesale — tax exempt", "company_id": lead.company_id.id or self.env.company.id})
        lead.action_grant_tax_exemption()
        self.assertEqual(base64.b64decode(partner.with_context(bin_size=False).x_tax_exemption_document), PDF)
        self.assertEqual(partner.x_tax_exemption_document_filename, "resale.pdf")

    def test_tab_and_menu_are_on_the_form(self):
        arch = self.env.ref("int_crm_customizations.crm_lead_view_form_tax_exemption").arch
        self.assertIn('widget="int_lead_documents"', arch)
        self.assertIn('name="int_documents"', arch)
        self.assertNotIn('name="x_tax_exemption_document"', arch)
        self.assertTrue(self.env.ref("int_crm_customizations.int_lead_document_label_menu"))
