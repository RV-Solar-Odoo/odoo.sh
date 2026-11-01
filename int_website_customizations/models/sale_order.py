from odoo import models

# Checkout stores the brand on the transaction, but the confirmation email
# prints the provider name ("Stripe"). These are the names customers expect.
_METHOD_LABELS = {
    "visa": "Visa",
    "mastercard": "Mastercard",
    "amex": "American Express",
    "discover": "Discover",
    "diners": "Diners Club",
    "jcb": "JCB",
    "unionpay": "UnionPay",
    "ach_direct_debit": "Bank transfer",
    "wire_transfer": "Bank transfer",
    "sepa_direct_debit": "Bank transfer",
    "bacs_direct_debit": "Bank transfer",
    "becs_direct_debit": "Bank transfer",
}


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _action_confirm(self):
        """Keep an in-store pickup as fulfillment data, not a customer address.

        ``delivery`` turns every pickup point into a child delivery contact when
        an order is confirmed. That is useful for a carrier's locker, but an
        in-store order already carries its store in ``pickup_location_data`` and
        ``warehouse_id``. Temporarily hiding that data prevents the generic
        pickup-point contact from being created. The selected store is restored
        after confirmation, while the customer remains the contact on the order
        and its stock transfers.
        """
        in_store_orders = self.filtered(
            lambda order: (
                order.carrier_id.delivery_type == "in_store"
                and order.pickup_location_data
            )
        )
        pickup_data = {
            order.id: dict(order.pickup_location_data)
            for order in in_store_orders
        }
        fiscal_positions = {
            order.id: order.fiscal_position_id
            for order in in_store_orders
        }
        previous_shipping = {
            order.id: order.partner_shipping_id
            for order in in_store_orders
        }

        if in_store_orders:
            in_store_orders.with_context(tracking_disable=True).write({
                "pickup_location_data": False,
            })
        try:
            result = super()._action_confirm()
        finally:
            for order in in_store_orders.exists():
                order.with_context(tracking_disable=True).write({
                    "pickup_location_data": pickup_data[order.id],
                })

        for order in in_store_orders.exists():
            values = {"partner_shipping_id": order.partner_id.id}
            if fiscal_positions[order.id]:
                values["fiscal_position_id"] = fiscal_positions[order.id].id
            order.with_context(
                update_delivery_shipping_partner=True,
                tracking_disable=True,
                mail_notrack=True,
            ).write(values)

            old_shipping = previous_shipping[order.id]
            if (
                old_shipping != order.partner_id
                and old_shipping.name
                and old_shipping.name.startswith(
                    "Anonymous express checkout partner for order "
                )
            ):
                old_shipping.active = False

        return result

    def _int_receipt_payment_method(self, tx):
        """Name to print as Payment Method on the checkout receipt."""
        self.ensure_one()
        if not tx:
            return ""
        tx = tx.sudo()
        method = tx.payment_method_id
        code = (method.code or "").casefold()
        if code in _METHOD_LABELS:
            return _METHOD_LABELS[code]
        if method and code not in ("card", "stripe") and method.name:
            return method.name
        if tx.token_id.payment_details:
            return tx.token_id.payment_details
        if method and method.name:
            return method.name
        return tx.provider_id.name or ""
