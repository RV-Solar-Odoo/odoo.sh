from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _add_delivery_cost_to_so(self):
        """A follow-up shipment must not add a second shipping charge.

        Checkout already priced the whole order. The backorder's label is ours to buy.
        """
        self.ensure_one()
        sale = self.sale_id
        if self.backorder_id and sale and sale.order_line.filtered(
            lambda line: line.is_delivery and not line.currency_id.is_zero(line.price_unit)
        ):
            return
        return super()._add_delivery_cost_to_so()
