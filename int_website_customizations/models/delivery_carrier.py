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
        if not super()._is_available_for_order(order):
            return False
        amount = self._int_order_amount_without_delivery(order)
        if self.int_min_order_amount and amount + 1e-6 < self.int_min_order_amount:
            return False
        if (
            self.delivery_type == "shippo"
            and getattr(self, "int_shippo_provider", False)
            and self._int_free_shipping_applies(order, amount)
        ):
            return False
        return True

    def _int_free_shipping_applies(self, order, amount=None):
        if amount is None:
            amount = self._int_order_amount_without_delivery(order)
        free_methods = self.search([
            ("int_min_order_amount", ">", 0),
            ("id", "!=", self.id),
        ])
        if "is_published" in self._fields:
            free_methods = free_methods.filtered("is_published")
        return any(amount + 1e-6 >= method.int_min_order_amount for method in free_methods)
