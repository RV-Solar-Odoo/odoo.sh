from lxml import etree
from lxml import html

from odoo.tests import TransactionCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


@tagged("-at_install", "post_install")
class TestPortalSecurity(TransactionCase):

    def _arch(self, xmlid):
        return self.env.ref(xmlid).get_combined_arch()

    def _website(self):
        website = self.env["website"].search([], limit=1)
        if not website:
            website = self.env["website"].create({"name": "Portal Security Test"})
        return website

    def _render(self, template, values=None):
        website = self._website()
        qcontext = {"main_object": website}
        qcontext.update(values or {})
        with MockRequest(self.env, website=website) as req:
            req.is_frontend = True
            return str(self.env["ir.qweb"]._render(template, qcontext))

    def test_portal_home_renames_the_security_card(self):
        arch = self._arch("portal.portal_my_home")
        self.assertIn("Password &amp; Security", arch)
        self.assertNotIn("Connection &amp; Security", arch)
        self.assertNotIn("Connection & Security", arch)

        rendered = self._render("portal.portal_my_home")
        plain = rendered.replace("&amp;", "&")
        self.assertIn("Password & Security", plain)
        self.assertNotIn("Connection & Security", plain)

        card = html.fromstring(rendered).xpath("//a[@href='/my/security']")[0]
        self.assertEqual(card.get("title"), "Password & Security")
        self.assertIn("Password & Security", " ".join(card.itertext()))
        self.assertIn("Configure your connection parameters", " ".join(card.itertext()))

    def test_security_page_heading_breadcrumb_and_blank_passwords(self):
        arch = etree.fromstring(self._arch("portal.portal_my_security"))
        self.assertNotIn("no_breadcrumbs", etree.tostring(arch, encoding="unicode"))
        title = arch.xpath("//t[@t-set='additional_title']")
        self.assertEqual(len(title), 1)
        self.assertEqual("".join(title[0].itertext()).strip(), "Password & Security")
        page_name = arch.xpath("//t[@t-set='page_name']")
        self.assertEqual(page_name[0].get("t-value"), "'my_security'")
        # A direct child of the t-call, so the layout sees it before drawing.
        self.assertEqual(title[0].getparent().get("t-call"), "portal.portal_layout")
        heading = arch.xpath("//h3")[0]
        self.assertEqual("".join(heading.itertext()).strip(), "Password & Security")

        expected = {
            "current": "current-password",
            "new": "new-password",
            "new2": "new-password",
        }
        for element_id, autocomplete in expected.items():
            field = arch.xpath(f"//input[@id='{element_id}']")[0]
            self.assertEqual(field.get("autocomplete"), autocomplete)
            self.assertEqual(field.get("t-att-value"), "''")
        deactivate = arch.xpath("//form[@id='portal_deactivate_account_form']//input[@name='password']")[0]
        self.assertIsNone(deactivate.get("t-att-value"))
        self.assertIsNone(deactivate.get("autocomplete"))

        crumbs = etree.fromstring(self._arch("portal.portal_breadcrumbs"))
        crumb = crumbs.xpath("//li[@t-if=\"page_name == 'my_security'\"]")[0]
        self.assertEqual(crumb.get("class"), "breadcrumb-item")
        self.assertEqual("".join(crumb.itertext()).strip(), "Password & Security")
        home = crumbs.xpath("//a[@href='/my/home']/parent::li")[0]
        self.assertIs(crumb.getprevious(), home)

        rendered = self._render("portal.portal_my_security", {
            "errors": {},
            "get_error": lambda *args: None,
            "success": {},
            "debug": False,
            "page_name": "home",
        })
        tree = html.fromstring(rendered)
        heading = tree.xpath("//div[contains(@class, 'o_portal_security_body')]//h3")[0]
        self.assertEqual(" ".join(heading.itertext()).strip(), "Password & Security")
        self.assertIn("Password & Security", " ".join(tree.xpath("//title")[0].itertext()))
        self.assertNotIn("Connection & Security", rendered.replace("&amp;", "&"))
        self.assertTrue(any(
            "Password & Security" in " ".join(li.itertext())
            for li in tree.xpath("//ol[contains(@class, 'breadcrumb')]//li")
        ))
        for element_id, autocomplete in expected.items():
            field = tree.xpath(f"//input[@id='{element_id}']")[0]
            self.assertEqual(field.get("value"), "")
            self.assertEqual(field.get("autocomplete"), autocomplete)
            self.assertIn('value=""', html.tostring(field, encoding="unicode"))

    def test_reset_password_fields_are_blank(self):
        arch = etree.fromstring(self._arch("auth_signup.fields"))
        for element_id in ("password", "confirm_password"):
            field = arch.xpath(f"//input[@id='{element_id}']")[0]
            self.assertEqual(field.get("autocomplete"), "new-password")
            self.assertEqual(field.get("t-att-value"), "''")

        rendered = self._render("auth_signup.fields")
        # The template is two sibling divs, not a full document.
        tree = html.fragment_fromstring(rendered, create_parent="div")
        for element_id in ("password", "confirm_password"):
            field = tree.xpath(f"//input[@id='{element_id}']")[0]
            self.assertEqual(field.get("type"), "password")
            self.assertEqual(field.get("value"), "")
            self.assertEqual(field.get("autocomplete"), "new-password")
            self.assertIn('value=""', html.tostring(field, encoding="unicode"))

    def test_layout_marks_approved_dealers(self):
        arch = self._arch("website.layout")
        self.assertIn("o_int_approved_dealer", arch)
        self.assertIn("_int_is_dealer_contact", arch)
        self.assertIn("document.documentElement.classList.add", arch)
