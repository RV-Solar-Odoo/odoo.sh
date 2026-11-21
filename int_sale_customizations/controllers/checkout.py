from urllib.parse import quote

from psycopg2.errors import LockNotAvailable

from odoo import _
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.fields import Command
from odoo.http import request, route
from odoo.tools import SQL
from odoo.tools.translate import _lt

from odoo.addons.website_sale.controllers.cart import Cart
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.payment import PaymentPortal


class BackorderCart(Cart):

    @route(route="/shop/cart", type="http", auth="public", website=True, sitemap=False)
    def cart(self, id=None, access_token=None, revive_method="", **post):
        # A cart split at the payment step goes back to one line per product here.
        if request.cart:
            request.cart._int_backorder_merge()
        return super().cart(id=id, access_token=access_token, revive_method=revive_method, **post)


class BackorderCheckout(WebsiteSale):

    @route(
        "/shop/payment", type="http", auth="public", website=True, sitemap=False,
        list_as_website_content=_lt("Shop Payment"),
    )
    def shop_payment(self, **post):
        if request.cart:
            request.cart._int_backorder_merge()
        return super().shop_payment(**post)

    def _get_shop_payment_values(self, order, **kwargs):
        """Split backordered quantities off, then charge only what ships now.

        Runs after the cart is recomputed, so prices, taxes and shipping are current.
        The split is what fixes the pay-now amount for this visit to the payment page.
        """
        order._int_backorder_split()
        values = super()._get_shop_payment_values(order, **kwargs)
        pay_now = order._int_pay_now_amount()
        if order._int_backorder_lines():
            values["amount"] = pay_now
        values.update({
            "int_pay_now": pay_now,
            "int_backorder_amount": order._int_backorder_amount(),
            "int_terms": order._int_terms_for(request.env.user),
            "int_error": request.params.get("int_error") or "",
        })
        return values

    @route("/shop/payment/validate", type="http", auth="public", website=True, sitemap=False)
    def shop_payment_validate(self, sale_order_id=None, **post):
        """A cart that is all backorder has nothing to pay. Confirm it here."""
        order = request.cart if sale_order_id is None else None
        if (
            order
            and order.state in ("draft", "sent")
            and order._int_backorder_lines()
            and not order._int_pay_now_amount()
            and not order.get_portal_last_transaction()
        ):
            try:
                order._int_place_without_payment("backorder", request.env.user)
            except (UserError, ValidationError) as exc:
                return request.redirect("/shop/payment?int_error=%s" % quote(str(exc.args[0])))
            request.website.sale_reset()
            return request.redirect("/shop/confirmation")
        return super().shop_payment_validate(sale_order_id=sale_order_id, **post)

    @route("/shop/int_on_account", type="http", methods=["POST"], auth="user", website=True, sitemap=False)
    def int_shop_on_account(self, **post):
        """Place Order on Account: confirm the cart on the dealer's payment terms."""
        order = request.cart
        if not order:
            return request.redirect("/shop/cart")
        try:
            order._int_place_without_payment("account", request.env.user)
        except (UserError, ValidationError) as exc:
            return request.redirect("/shop/payment?int_error=%s" % quote(str(exc.args[0])))
        request.website.sale_reset()
        return request.redirect("/shop/confirmation")


class BackorderPaymentPortal(PaymentPortal):

    @route("/shop/payment/transaction/<int:order_id>", type="jsonrpc", auth="public", website=True)
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        """Charge the pay-now amount when part of the cart is backordered.

        Odoo only accepts the full order total here. This is the same route with the
        backorder lines left out of the amount; any other cart goes to Odoo unchanged.
        """
        try:
            order_sudo = self._document_check_access("sale.order", order_id, access_token)
        except MissingError:
            raise
        except AccessError as e:
            raise ValidationError(_("The access token is invalid.")) from e
        if order_sudo.state not in ("draft", "sent") or not order_sudo._int_backorder_lines():
            return super().shop_payment_transaction(order_id, access_token, **kwargs)
        try:
            request.env.cr.execute(
                SQL("SELECT 1 FROM sale_order WHERE id = %s FOR NO KEY UPDATE NOWAIT", order_id)
            )
        except LockNotAvailable:
            raise UserError(_("Payment is already being processed."))

        order_sudo._check_cart_is_ready_to_be_paid()
        if order_sudo.int_on_account:
            order_sudo.int_on_account = False

        self._validate_transaction_kwargs(kwargs)
        kwargs.update({
            "partner_id": order_sudo.partner_invoice_id.id,
            "currency_id": order_sudo.currency_id.id,
            "sale_order_id": order_id,
        })
        pay_now = order_sudo._int_pay_now_amount()
        if not kwargs.get("amount"):
            kwargs["amount"] = pay_now
        compare_amounts = order_sudo.currency_id.compare_amounts
        if compare_amounts(kwargs["amount"], pay_now):
            raise ValidationError(_("The cart has been updated. Please refresh the page."))
        if compare_amounts(order_sudo.amount_paid, pay_now) >= 0:
            raise UserError(_("The cart has already been paid. Please refresh the page."))

        if delay_token_charge := kwargs.get("flow") == "token":
            request.update_context(delay_token_charge=True)
        tx_sudo = self._create_transaction(
            custom_create_values={"sale_order_ids": [Command.set([order_id])]}, **kwargs,
        )
        request.session["__website_sale_last_tx_id"] = tx_sudo.id
        self._validate_transaction_for_order(tx_sudo, order_sudo)
        if delay_token_charge:
            tx_sudo._charge_with_token()
        return tx_sudo._get_processing_values()
