from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale


class RvsbCheckoutAccount(WebsiteSale):

    @route('/shop/rvsb/create_account', type='jsonrpc', auth='public', website=True, sitemap=False)
    def rvsb_create_account(self):
        """Create the account the guest asked for on the order confirmation page.

        The order comes from the session, as on `/shop/confirmation`, so a guest can only
        act on the order they just placed.
        """
        order_sudo = request.env['sale.order'].sudo().browse(
            request.session.get('sale_last_order_id')
        ).exists()
        if not order_sudo or not request.website.is_public_user():
            return 'failed'
        # 'sent' = order placed with a pending payment (e.g. wire transfer),
        # 'sale' = order confirmed. Either way the checkout is finished.
        if order_sudo.state not in ('sent', 'sale'):
            return 'failed'
        if not order_sudo.rvsb_account_status:
            order_sudo._rvsb_invite_customer()
        return order_sudo.rvsb_account_status
