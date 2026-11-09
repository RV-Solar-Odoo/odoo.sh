from odoo.fields import Command
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestDealerSections(HttpCase):
    """html.o_int_approved_dealer drives the dealer-only home page sections."""

    MARKER = "classList.add('o_int_approved_dealer')"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        company = cls.website.company_id
        public_partner = cls.env.ref("base.public_user").partner_id
        public_pl = public_partner.with_company(company).property_product_pricelist
        if not public_pl:
            public_pl = cls.env["product.pricelist"].create({"name": "Sections Public"})
            public_partner.with_company(company).specific_property_product_pricelist = public_pl
        dealer_pl = cls.env["product.pricelist"].create({"name": "Sections Dealer"})
        cls.users = {}
        for key, pricelist in (("dealer", dealer_pl), ("retail", public_pl), ("pending", public_pl)):
            partner = cls.env["res.partner"].create({"name": f"Sections {key}"})
            partner.with_company(company).specific_property_product_pricelist = pricelist
            cls.users[key] = cls.env["res.users"].with_context(no_reset_password=True).create({
                "name": partner.name,
                "login": f"sections-{key}",
                "password": f"sections-{key}-pass",
                "partner_id": partner.id,
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
            })

    def _home(self, key=None):
        if key:
            self.authenticate(f"sections-{key}", f"sections-{key}-pass")
        response = self.url_open("/")
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_public_visitor_has_no_dealer_class(self):
        self.assertNotIn(self.MARKER, self._home())

    def test_retail_and_pending_users_have_no_dealer_class(self):
        self.assertNotIn(self.MARKER, self._home("retail"))
        self.assertNotIn(self.MARKER, self._home("pending"))

    def test_approved_dealer_has_the_class_in_the_head(self):
        page = self._home("dealer")
        self.assertIn(self.MARKER, page)
        self.assertLess(page.index(self.MARKER), page.index("<body"))
