from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.float_utils import float_round


class PickingSplit(models.TransientModel):
    _name = "int.picking.split"
    _description = "Split a delivery without dropping serial numbers"

    picking_id = fields.Many2one("stock.picking", required=True)
    line_ids = fields.One2many("int.picking.split.line", "wizard_id")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking = self.env["stock.picking"].browse(res.get("picking_id"))
        if picking and "line_ids" in fields_list:
            res["line_ids"] = [
                Command.create(self._line_vals(move))
                for move in picking.move_ids.filtered(
                    lambda move: move.state not in ("done", "cancel")
                    and move.product_uom.compare(move.product_uom_qty, 0) > 0
                )
            ]
        return res

    @api.model
    def _line_vals(self, move):
        names = move.move_line_ids.lot_id.mapped("name")
        serials = ", ".join(names[:8])
        if len(names) > 8:
            serials += self.env._(" (+%(extra)s more)", extra=len(names) - 8)
        return {
            "move_id": move.id,
            "demand_qty": move.product_uom_qty,
            "reserved_qty": move.quantity,
            "serials": serials,
        }

    def action_split(self):
        self.ensure_one()
        picking = self.picking_id
        lines = self.line_ids.filtered(lambda line: line.move_id.product_uom.compare(line.split_qty, 0) > 0)
        if not lines:
            raise UserError(self.env._("Enter the quantity to split onto the new delivery."))
        for line in lines:
            move = line.move_id
            if move.product_uom.compare(line.split_qty, line.demand_qty) > 0:
                raise UserError(self.env._(
                    "You can split at most %(qty)s %(uom)s of %(product)s.",
                    qty=line.demand_qty,
                    uom=move.product_uom.name,
                    product=move.product_id.display_name,
                ))
        if all(
            line.move_id.product_uom.compare(line.split_qty, line.demand_qty) == 0
            for line in self.line_ids
        ):
            raise UserError(self.env._("Leave at least one unit on this delivery."))

        new_picking = picking.copy({
            "name": "/",
            "move_ids": [],
            "move_line_ids": [],
            "backorder_id": picking.id,
            "carrier_tracking_ref": False,
        })
        moved = []
        for line in lines:
            self._split_move(line.move_id, line.split_qty, new_picking)
            moved.append("%s %s" % (
                float_round(line.split_qty, precision_rounding=line.move_id.product_uom.rounding),
                line.move_id.product_id.display_name,
            ))
        body = self.env._(
            "Split %(qty)s onto %(delivery)s. Serial numbers already selected stayed on those units.",
            qty=", ".join(moved),
            delivery=new_picking._get_html_link(),
        )
        picking.message_post(body=body)
        new_picking.message_post(body=self.env._(
            "Split from %(delivery)s.",
            delivery=picking._get_html_link(),
        ))
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": new_picking.id,
            "view_mode": "form",
            "target": "current",
        }

    def _split_move(self, move, split_qty, new_picking):
        """Move `split_qty` onto `new_picking`, taking the existing reservations with it."""
        if move.product_uom.compare(split_qty, move.product_uom_qty) == 0:
            move.write({"picking_id": new_picking.id})
            move.move_line_ids.write({"picking_id": new_picking.id})
            return
        qty = move.product_uom._compute_quantity(
            split_qty, move.product_id.uom_id, rounding_method="HALF-UP",
        )
        vals = move._split(qty)
        if not vals:
            raise UserError(self.env._(
                "Could not split %(product)s.",
                product=move.product_id.display_name,
            ))
        vals = vals[0]
        vals["picking_id"] = new_picking.id
        new_move = self.env["stock.move"].create(vals)
        self._move_reserved_lines(move, split_qty, new_move)
        move._recompute_state()
        new_move._recompute_state()
        if new_move.state == "draft":
            new_move.state = "confirmed"

    def _move_reserved_lines(self, move, split_qty, new_move):
        """Reattach reserved lines, lots first, so a picked serial is not unreserved."""
        remaining = split_qty
        uom = move.product_uom
        lines = move.move_line_ids.sorted(key=lambda line: (not line.lot_id, line.id))
        for line in lines:
            if uom.compare(remaining, 0) <= 0:
                break
            if line.product_uom_id.compare(line.quantity, 0) <= 0:
                continue
            line_qty = line.product_uom_id._compute_quantity(line.quantity, uom, round=False)
            if uom.compare(line_qty, remaining) <= 0:
                line.write({"move_id": new_move.id, "picking_id": new_move.picking_id.id})
                remaining = float_round(remaining - line_qty, precision_rounding=uom.rounding)
                continue
            take = min(
                line.quantity,
                uom._compute_quantity(remaining, line.product_uom_id, rounding_method="HALF-UP"),
            )
            if line.product_uom_id.compare(take, 0) <= 0:
                break
            # Free the reservation before the new line takes it for the same lot.
            line.quantity -= take
            self.env["stock.move.line"].create({
                "move_id": new_move.id,
                "picking_id": new_move.picking_id.id,
                "product_id": line.product_id.id,
                "product_uom_id": line.product_uom_id.id,
                "quantity": take,
                "lot_id": line.lot_id.id,
                "lot_name": line.lot_name,
                "location_id": line.location_id.id,
                "location_dest_id": line.location_dest_id.id,
                "package_id": line.package_id.id,
                "result_package_id": line.result_package_id.id,
                "owner_id": line.owner_id.id,
                "picked": line.picked,
            })
            remaining = 0


class PickingSplitLine(models.TransientModel):
    _name = "int.picking.split.line"
    _description = "Delivery split line"

    wizard_id = fields.Many2one("int.picking.split", required=True, ondelete="cascade")
    move_id = fields.Many2one("stock.move", required=True)
    product_id = fields.Many2one(related="move_id.product_id")
    product_uom_id = fields.Many2one(related="move_id.product_uom")
    demand_qty = fields.Float(string="Demand", digits="Product Unit")
    reserved_qty = fields.Float(string="Reserved", digits="Product Unit")
    serials = fields.Char(string="Serial numbers")
    split_qty = fields.Float(
        string="Split off",
        digits="Product Unit",
        help="Quantity to move onto the new delivery. Serial numbers already selected on that quantity go with it.",
    )
