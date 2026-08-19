from odoo import fields, models


class ShippoBox(models.Model):
    _name = "int.shippo.box"
    _description = "Shippo box"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    length_in = fields.Float(string="Length (in)", required=True)
    width_in = fields.Float(string="Width (in)", required=True)
    height_in = fields.Float(string="Height (in)", required=True)
    empty_lb = fields.Float(string="Empty weight (lb)")
    max_lb = fields.Float(string="Max weight (lb)")
