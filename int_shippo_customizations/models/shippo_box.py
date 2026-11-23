from odoo import api, fields, models


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

    @api.model
    def suggest_for_items(self, items, weight_lb):
        """Pick the smallest box that fits item dimensions, volume, and weight.

        items: iterable of (length_in, width_in, height_in, qty)
        Falls back to the smallest box when nothing fits.
        """
        box = self.fitting_box_for_items(items, weight_lb)
        if box:
            return box
        return self._int_boxes().sorted(lambda b: b.length_in * b.width_in * b.height_in)[:1]

    @api.model
    def _int_boxes(self):
        return self.search([
            ("length_in", ">", 0),
            ("width_in", ">", 0),
            ("height_in", ">", 0),
        ])

    @api.model
    def fitting_box_for_items(self, items, weight_lb):
        """The smallest box the items really fit in, or an empty recordset."""
        boxes = self._int_boxes()
        if not boxes:
            return self.browse()
        max_l = max_w = max_h = 0.0
        volume = 0.0
        for length, width, height, qty in items:
            dims = sorted((length or 0.0, width or 0.0, height or 0.0), reverse=True)
            max_l = max(max_l, dims[0])
            max_w = max(max_w, dims[1])
            max_h = max(max_h, dims[2])
            volume += (length or 0.0) * (width or 0.0) * (height or 0.0) * (qty or 0.0)
        fits = []
        for box in boxes:
            outer = sorted((box.length_in, box.width_in, box.height_in), reverse=True)
            if max_l and (outer[0] + 1e-6 < max_l or outer[1] + 1e-6 < max_w or outer[2] + 1e-6 < max_h):
                continue
            if volume and box.length_in * box.width_in * box.height_in + 1e-6 < volume:
                continue
            if box.max_lb and (weight_lb or 0.0) + (box.empty_lb or 0.0) > box.max_lb + 1e-6:
                continue
            fits.append((box.length_in * box.width_in * box.height_in, box))
        if not fits:
            return self.browse()
        fits.sort(key=lambda item: item[0])
        return fits[0][1]
