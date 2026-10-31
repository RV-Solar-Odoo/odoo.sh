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
