from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    int_min_order_amount = fields.Float(
        string="Available only above",
        help="Hide this method unless the order total (without shipping) is at least this amount.",
    )

    def _int_order_amount_without_delivery(self, order):
        if hasattr(order, "_compute_amount_total_without_delivery"):
            return order._compute_amount_total_without_delivery()
        delivery_total = sum(order.order_line.filtered("is_delivery").mapped("price_total"))
        return order.amount_total - delivery_total

    def _is_available_for_order(self, order):
        amount = self._int_order_amount_without_delivery(order)
        if self.int_min_order_amount and amount + 1e-6 < self.int_min_order_amount:
            return False
        return super()._is_available_for_order(order)
