import base64
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class DealerDocumentsCommon:

    @classmethod
    def _setup_dealers(cls):
        env = cls.env
        cls.website = env.ref("website.default_website")
        cls.company = cls.website.company_id
        public = env.ref("base.public_user").partner_id.commercial_partner_id
        cls.public_pl = public.with_company(cls.company).property_product_pricelist
        if not cls.public_pl:
            cls.public_pl = env["product.pricelist"].create({"name": "Documents Public"})
            public.with_company(cls.company).specific_property_product_pricelist = cls.public_pl
        cls.dealer_pl = env["product.pricelist"].create({"name": "Documents Dealer"})
        cls.manager = env["res.users"].with_context(no_reset_password=True).create({
            "name": "Documents Manager",
            "login": "documents-manager@example.com",
            "email": "documents-manager@example.com",
            "company_id": cls.company.id,
            "company_ids": [Command.set([cls.company.id])],
            "group_ids": [Command.set([env.ref("sales_team.group_sale_manager").id])],
        })
        cls.utah = env["res.country.state"].search([("code", "=", "UT"), ("country_id", "=", env.ref("base.us").id)], limit=1)
        cls.dealer = cls._dealer("Documents Dealer Co")
        cls.dealer.user_id = cls.manager
        cls.owner = cls._login(cls.dealer, "documents-owner@example.com", "owner")
        cls.accountant = cls._login(cls.dealer, "documents-accountant@example.com", "accountant")
        cls.buyer = cls._login(cls.dealer, "documents-buyer@example.com", "buyer")
        cls.viewer = cls._login(cls.dealer, "documents-viewer@example.com", "viewer")
        cls.other_dealer = cls._dealer("Documents Other Co")
        cls.other_owner = cls._login(cls.other_dealer, "documents-other@example.com", "owner")

        Label = env["int.lead.document.label"]
        cls.license_label = Label._int_by_code("business_license")
        cls.agreement_label = Label._int_by_code("dealer_agreement")
        cls.lead = env["crm.lead"].create({
            "name": "Documents Application",
            "partner_id": cls.dealer.id,
            "company_id": cls.company.id,
            "user_id": cls.manager.id,
        })
        cls.license_doc = cls._lead_document(cls.lead, cls.license_label, "license.pdf")
        other_lead = env["crm.lead"].create({
            "name": "Other Application", "partner_id": cls.other_dealer.id, "company_id": cls.company.id,
        })
        cls.other_doc = cls._lead_document(other_lead, cls.license_label, "other-license.pdf")

    @classmethod
    def _dealer(cls, name):
        partner = cls.env["res.partner"].create({
            "name": name, "is_company": True, "email": f"{name.split()[1].lower()}@example.com",
            "country_id": cls.env.ref("base.us").id,
        })
        partner.with_company(cls.company).specific_property_product_pricelist = cls.dealer_pl
        return partner

    @classmethod
    def _login(cls, company_partner, login, role):
        contact = cls.env["res.partner"].create({
            "name": login.split("@")[0], "parent_id": company_partner.id, "email": login, "int_portal_role": role,
        })
        return cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": contact.name,
            "login": login,
            "password": login,
            "partner_id": contact.id,
            "company_id": cls.company.id,
            "company_ids": [Command.set([cls.company.id])],
            "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
        })

    @classmethod
    def _lead_document(cls, lead, label, name):
        return cls.env["int.lead.document"].with_context(int_document_no_log=True).create({
            "lead_id": lead.id,
            "label_id": label.id,
            "upload": base64.b64encode(PDF),
            "upload_name": name,
        })

    def _submit(self, user, replaces=None, **values):
        values = {"cert_type": "resale", "state_id": str(self.utah.id), **values}
        return self.env["int.dealer.certificate"]._int_portal_submit(
            user, self.company, values, "cert.pdf", PDF, replaces=replaces,
        )


@tagged("post_install", "-at_install")
class TestDealerDocuments(DealerDocumentsCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_dealers()

    def test_application_documents_come_live_from_the_lead(self):
        documents = self.dealer._int_application_documents(self.company)
        self.assertEqual(documents, self.license_doc)
        self.assertNotIn(self.other_doc, documents)
        self.assertFalse(self.dealer._int_dealer_agreement(self.company))

        agreement = self._lead_document(self.lead, self.agreement_label, "agreement.pdf")
        self.assertEqual(self.dealer._int_dealer_agreement(self.company), agreement)
        self.assertNotIn(agreement, self.dealer._int_application_documents(self.company))

    def test_replacing_an_application_file_keeps_the_label_and_needs_review(self):
        with self.assertRaises(AccessError):
            self.license_doc._int_portal_replace(self.buyer, "new.pdf", PDF)
        new = self.license_doc._int_portal_replace(self.accountant, "new.pdf", PDF)
        self.assertEqual(new.label_id, self.license_label)
        self.assertEqual(new.lead_id, self.lead)
        self.assertEqual(new.int_replaces_id, self.license_doc)
        self.assertFalse(new.reviewed)
        self.assertEqual(self.dealer._int_application_documents(self.company), new)
        self.assertIn(self.license_doc, self.lead.int_document_ids)
        self.assertTrue(self.lead.activity_ids.filtered(lambda act: act.user_id == self.manager))

    def test_replaced_certificate_stays_valid_until_the_new_one_is_approved(self):
        with self.assertRaises(AccessError):
            self._submit(self.buyer)
        first = self._submit(self.owner, cert_number="R-1")
        self.assertEqual(first.status, "pending_review")
        self.assertTrue(first.activity_ids.filtered(lambda act: act.user_id == self.manager))
        with self.assertRaises(AccessError):
            first.with_user(self.owner).action_approve()
        first.with_user(self.manager).action_approve()
        self.assertEqual(first.status, "valid")
        self.assertEqual(first.reviewed_by_id, self.manager)
        with self.assertRaises(UserError):
            self._submit(self.owner)

        second = self._submit(self.accountant, replaces=first, cert_number="R-2")
        self.assertEqual((second.status, first.status), ("pending_review", "valid"))
        self.assertEqual((second.cert_type, second.state_id), (first.cert_type, first.state_id))
        with self.assertRaises(UserError):
            self._submit(self.owner, replaces=first)
        second.with_user(self.manager).action_approve()
        self.assertEqual((first.status, second.status), ("superseded", "valid"))
        listed = self.env["int.dealer.certificate"]._int_dealer_certificates(self.dealer, self.company)
        self.assertEqual(listed, second)

    def test_reject_needs_a_note_and_emails_the_dealer(self):
        cert = self._submit(self.owner)
        with self.assertRaises(UserError):
            cert.with_user(self.manager).action_reject()
        cert.review_note = "The file is unreadable."
        cert.with_user(self.manager).action_reject()
        self.assertEqual(cert.status, "rejected")
        mail = self.env["mail.mail"].search([("model", "=", cert._name), ("res_id", "=", cert.id)])
        self.assertIn(self.owner.partner_id, mail.recipient_ids)
        self.assertIn(self.accountant.partner_id, mail.recipient_ids)
        self.assertNotIn(self.buyer.partner_id, mail.recipient_ids)

    def test_reminders_go_out_once_per_threshold_then_it_expires(self):
        today = fields.Date.context_today(self.env["int.dealer.certificate"])
        self.company.int_cert_reminder_days = "60,30,7"
        cert = self._submit(self.owner, expiration_date=str(today + timedelta(days=45)))
        cert.with_user(self.manager).action_approve()
        self.assertEqual(cert.status, "expiring")

        def mails():
            return self.env["mail.mail"].search_count([
                ("model", "=", cert._name),
                ("res_id", "=", cert.id),
                ("recipient_ids", "in", self.owner.partner_id.ids),
            ])

        Cert = self.env["int.dealer.certificate"]
        Cert._int_cron_certificates()
        self.assertEqual((mails(), cert.reminder_sent_days), (1, "60"))
        Cert._int_cron_certificates()
        self.assertEqual(mails(), 1)
        cert.expiration_date = today + timedelta(days=5)
        Cert._int_cron_certificates()
        self.assertEqual((mails(), cert.reminder_sent_days), (2, "60,30,7"))
        cert.expiration_date = today - timedelta(days=1)
        Cert._int_cron_certificates()
        self.assertEqual((mails(), cert.status), (3, "expired"))

    def test_uploads_are_checked(self):
        with self.assertRaises(UserError):
            self.env["int.dealer.certificate"]._int_portal_submit(
                self.owner, self.company, {"cert_type": "other"}, "cert.pdf", b"not a pdf at all",
            )
        with self.assertRaises(UserError):
            self.env["int.dealer.certificate"]._int_portal_submit(
                self.owner, self.company, {"cert_type": "other"}, "cert.exe", PDF,
            )
        with self.assertRaises(AccessError):
            self.dealer._int_portal_set_logo(self.accountant, "logo.png", PNG)
        with self.assertRaises(UserError):
            self.dealer._int_portal_set_logo(self.owner, "logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        self.dealer._int_portal_set_logo(self.owner, "logo.png", PNG)
        self.assertTrue(self.dealer.image_1920)

    def test_approved_tax_certificate_refreshes_the_contact_file(self):
        self.dealer.with_company(self.company).x_is_tax_exempt = True
        cert = self._submit(self.owner, cert_type="sales_tax_exemption")
        cert.with_user(self.manager).action_approve()
        self.assertEqual(self.dealer.with_company(self.company).x_tax_exemption_document_filename, "cert.pdf")


@tagged("post_install", "-at_install")
class TestDealerDocumentsPortal(DealerDocumentsCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_dealers()

    def test_every_role_sees_the_page_and_only_its_own_files(self):
        self.authenticate(self.viewer.login, self.viewer.login)
        page = self.url_open("/my/documents")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Application Documents", page.text)
        self.assertIn("Not signed yet", page.text)
        self.assertNotIn('action="/my/documents/certificates"', page.text)
        self.assertNotIn('action="/my/documents/logo"', page.text)
        own = self.url_open(f"/my/documents/file/application/{self.license_doc.id}")
        self.assertEqual(own.status_code, 200)
        other = self.url_open(f"/my/documents/file/application/{self.other_doc.id}")
        self.assertEqual(other.status_code, 404)

    def test_owner_gets_the_forms(self):
        self.authenticate(self.owner.login, self.owner.login)
        page = self.url_open("/my/documents")
        self.assertIn('action="/my/documents/certificates"', page.text)
        self.assertIn('action="/my/documents/logo"', page.text)
        home = self.url_open("/my")
        self.assertIn('href="/my/documents"', home.text)

    def test_retail_customers_have_no_documents_page(self):
        retail = self.env["res.partner"].create({"name": "Documents Retail", "email": "documents-retail@example.com"})
        retail.with_company(self.company).specific_property_product_pricelist = self.public_pl
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Documents Retail",
            "login": "documents-retail@example.com",
            "password": "documents-retail@example.com",
            "partner_id": retail.id,
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
        })
        self.authenticate(user.login, user.login)
        page = self.url_open("/my/documents", allow_redirects=False)
        self.assertIn(page.status_code, (302, 303))
        self.assertEqual(self.url_open(f"/my/documents/file/application/{self.license_doc.id}").status_code, 404)
