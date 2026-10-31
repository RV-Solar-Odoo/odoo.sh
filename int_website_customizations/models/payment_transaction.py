from odoo import models
from odoo.tools import str2bool


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _create_payment(self, **extra_create_values):
        """Invoice a paid website order without emailing the customer.

        Sales' Automatic Invoice setting also sends the invoice, so it stays
        off. The invoice is posted here so the payment can be matched to it.
        """
        self.ensure_one()
        if self._int_should_invoice_website_order():
            self._invoice_sale_orders()
            self.invoice_ids.filtered(lambda inv: inv.state == "draft").action_post()
        return super()._create_payment(**extra_create_values)

    def _int_should_invoice_website_order(self):
        self.ensure_one()
        if str2bool(self.env["ir.config_parameter"].sudo().get_param("sale.automatic_invoice")):
            return False
        if self.state != "done" or self.operation == "validation" or self.invoice_ids:
            return False
        orders = self.sale_order_ids.filtered(
            lambda so: so.website_id and so.state == "sale" and so.invoice_status != "invoiced"
        )
        return bool(orders)

    def _send_invoice(self):
        """Website invoices stay in Odoo. They are not emailed to the customer."""
        website_tx = self.filtered(lambda tx: tx.sale_order_ids.website_id)
        return super(PaymentTransaction, self - website_tx)._send_invoice()
