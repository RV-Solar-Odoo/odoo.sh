from odoo.fields import Command
from odoo.tests import HttpCase, tagged
from odoo.tools import file_open


@tagged("-at_install", "post_install")
class TestDealerSections(HttpCase):
    """Approved dealers get the dealer class and the dealer support section on the home page."""

    MARKER = "classList.add('o_int_approved_dealer')"
    SECTION = "o_int_dealer_support"

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
        page = self._home()
        self.assertNotIn(self.MARKER, page)
        self.assertNotIn(self.SECTION, page)

    def test_retail_and_pending_users_have_no_dealer_class(self):
        for key in ("retail", "pending"):
            page = self._home(key)
            self.assertNotIn(self.MARKER, page)
            self.assertNotIn(self.SECTION, page)

    def test_approved_dealer_has_the_class_in_the_head(self):
        page = self._home("dealer")
        self.assertIn(self.MARKER, page)
        self.assertLess(page.index(self.MARKER), page.index("<body"))
        self.assertIn(self.SECTION, page)
        self.assertIn("Your Dealer Support Center", page)
        self.assertIn('href="/my/help"', page)

    def test_only_the_bottom_dealer_section_is_hidden(self):
        # The hero also has a Become a Dealer button. Hiding every section with
        # that link hid the hero for dealers.
        scss = file_open("int_website_customizations/static/src/scss/dealer_home.scss").read()
        self.assertIn("#wrap > section.s_faq_list:has(", scss)
        self.assertNotIn("#wrap > section:has(", scss)

    def test_dealer_support_section_is_home_page_only(self):
        self.authenticate("sections-dealer", "sections-dealer-pass")
        response = self.url_open("/contactus")
        if response.status_code == 200:
            self.assertNotIn(self.SECTION, response.text)
