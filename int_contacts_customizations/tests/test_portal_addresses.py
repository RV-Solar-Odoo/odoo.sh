from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalAddresses(TransactionCase):

    def test_addresses_page_has_three_tabs_and_keeps_stock_hooks(self):
        arch = self.env.ref("portal.my_addresses").get_combined_arch()
        for tab in ("business", "customer", "billing"):
            self.assertIn(f"int_addr_pane_{tab}", arch)
        self.assertIn("int_contacts_customizations.portal_address_pane", arch)
        # The stock address script looks these up.
        for hook in ("use_delivery_as_billing", "billing_container", "o_add_billing_address_btn", "o_address_card_add_new"):
            self.assertIn(hook, arch)

    def test_address_card_tags_are_in_the_card_body(self):
        arch = self.env.ref("portal.address_card").get_combined_arch()
        self.assertIn("o_int_addr_body", arch)
        self.assertIn("o_int_addr_tags", arch)
        # Checkout's card is built on the portal card, so it gets the tags too.
        checkout = self.env.ref("website_sale.address_card", raise_if_not_found=False)
        if checkout:
            self.assertIn("o_int_addr_tags", checkout.get_combined_arch())
