from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale


class RvsbCheckoutAccount(WebsiteSale):

    def _rvsb_can_offer_account(self, order_sudo, partner_sudo=None):
        """Offer the checkbox only to guests, on the form for the order's main contact."""
        if not order_sudo or not request.website.is_public_user():
            return False
        if order_sudo._is_anonymous_cart():
            return True
        partner = order_sudo.partner_id
        return bool(partner_sudo) and partner_sudo == partner and not partner.user_ids

    def _prepare_address_form_values(self, *args, order_sudo=False, **kwargs):
        values = super()._prepare_address_form_values(*args, order_sudo=order_sudo, **kwargs)
        partner_sudo = args[0] if args else kwargs.get('partner_sudo')
        offer = self._rvsb_can_offer_account(order_sudo, partner_sudo)
        values['rvsb_offer_account'] = offer
        values['rvsb_create_account'] = bool(offer and order_sudo.rvsb_create_account)
        return values

    @route()
    def shop_address_submit(self, *args, **form_data):
        offered = form_data.pop('rvsb_account_offered', None)
        wants_account = form_data.pop('rvsb_create_account', None)
        order_sudo = request.cart
        was_anonymous = bool(order_sudo) and order_sudo._is_anonymous_cart()
        main_partner_before = order_sudo.partner_id if order_sudo else None

        response = super().shop_address_submit(*args, **form_data)

        # Only touch the choice when the checkbox was actually on the submitted form,
        # and the form edited the order's main contact.
        if offered and order_sudo and request.website.is_public_user():
            if was_anonymous or order_sudo.partner_id == main_partner_before:
                if not order_sudo.partner_id.user_ids:
                    order_sudo.rvsb_create_account = bool(wants_account)
        return response
