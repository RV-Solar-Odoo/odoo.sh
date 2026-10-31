from odoo import models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_split_transfer(self):
        # The standard split keeps whatever is typed as done and backorders the
        # rest without its move lines, so serials picked on the first step are lost.
        if len(self) == 1 and self.picking_type_code == "outgoing":
            return self.action_int_split_delivery()
        return super().action_split_transfer()

    def action_int_split_delivery(self):
        """Open the split wizard for this delivery."""
        self.ensure_one()
        if self.picking_type_code != "outgoing":
            raise UserError(self.env._("Only a delivery can be split this way."))
        if self.state in ("draft", "done", "cancel"):
            raise UserError(self.env._("This delivery can no longer be split."))
        if self.carrier_tracking_ref:
            raise UserError(self.env._(
                "This delivery already has a tracking number. Refund that label before splitting it."
            ))
        moves = self.move_ids.filtered(
            lambda move: move.state not in ("done", "cancel")
            and move.product_uom.compare(move.product_uom_qty, 0) > 0
        )
        if not moves:
            raise UserError(self.env._("There is nothing left on this delivery to split."))
        return {
            "name": self.env._("Split"),
            "type": "ir.actions.act_window",
            "res_model": "int.picking.split",
            "view_mode": "form",
            "target": "new",
            "context": {"default_picking_id": self.id},
        }
