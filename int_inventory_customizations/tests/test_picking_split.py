from odoo import Command
from odoo.tests import TransactionCase


class TestPickingSplit(TransactionCase):

    def test_split_uses_the_delivery_demand_when_the_form_drops_it(self):
        product = self.env["product.product"].create({
            "name": "Split Test Ekrano",
            "is_storable": True,
        })
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        picking_type = warehouse.out_type_id
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": picking_type.default_location_dest_id.id,
            "move_ids": [Command.create({
                "product_id": product.id,
                "product_uom_qty": 2,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
            })],
        })
        picking.action_confirm()
        move = picking.move_ids
        wizard = self.env["int.picking.split"].create({
            "picking_id": picking.id,
            "line_ids": [Command.create({
                "move_id": move.id,
                "demand_qty": 0,
                "split_qty": 1,
            })],
        })
        wizard.action_split()
        self.assertEqual(move.product_uom_qty, 1)
        new_move = self.env["stock.move"].search([
            ("product_id", "=", product.id),
            ("id", "!=", move.id),
            ("state", "!=", "cancel"),
        ])
        self.assertEqual(new_move.product_uom_qty, 1)
        self.assertNotEqual(new_move.picking_id, picking)
