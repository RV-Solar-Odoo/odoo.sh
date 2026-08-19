from odoo import api, fields, models
from odoo.exceptions import UserError


def _length_to_inches(value, uom_name):
    name = (uom_name or "").lower()
    if name in ("in", "inch", "inches", '"'):
        return value
    if "mm" in name:
        return value / 25.4
    if "cm" in name:
        return value / 2.54
    if "ft" in name or "foot" in name or "feet" in name:
        return value * 12.0
    return value / 0.0254


def _weight_to_lb(value, uom_name):
    name = (uom_name or "").lower()
    if name in ("lb", "lbs", "pound", "pounds"):
        return value
    if "oz" in name:
        return value / 16.0
    if name in ("g", "gram", "grams"):
        return value * 0.00220462
    return value * 2.20462


class StockPicking(models.Model):
    _inherit = "stock.picking"

    int_shippo_shipment_id = fields.Char(string="Shippo Shipment ID", copy=False)
    int_shippo_transaction_id = fields.Char(string="Shippo Transaction ID", copy=False)
    int_shippo_label_url = fields.Char(string="Shippo Label URL", copy=False)
    int_shippo_tracking_url = fields.Char(string="Shippo Tracking URL", copy=False)
    int_shippo_box_id = fields.Many2one(
        "int.shippo.box",
        string="Shippo Box",
        help="Carton sent to Shippo for rates. Suggested from product dimensions; warehouse can change it.",
    )

    def action_open_shippo_rates(self):
        self.ensure_one()
        if not self.int_shippo_box_id:
            self.int_shippo_box_id = self._int_shippo_suggest_box()
        wizard = self.env["int.shippo.rate.wizard"].create({
            "picking_id": self.id,
            "box_id": self.int_shippo_box_id.id,
        })
        wizard.action_refresh_dims()
        return {
            "name": self.env._("Shippo Rates"),
            "type": "ir.actions.act_window",
            "res_model": "int.shippo.rate.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def _int_shippo_address(self, partner):
        partner.ensure_one()
        missing = [
            label
            for field, label in (
                ("street", self.env._("street")),
                ("city", self.env._("city")),
                ("zip", self.env._("ZIP")),
                ("country_id", self.env._("country")),
            )
            if not partner[field]
        ]
        if missing:
            raise UserError(self.env._(
                "Complete the address for %(partner)s (%(fields)s) before requesting Shippo rates.",
                partner=partner.display_name,
                fields=", ".join(missing),
            ))
        return {
            "name": partner.name or partner.display_name,
            "street1": partner.street,
            "street2": partner.street2 or "",
            "city": partner.city,
            "state": partner.state_id.code or "",
            "zip": partner.zip,
            "country": partner.country_id.code,
            "phone": partner.phone or (partner.mobile if "mobile" in partner._fields else "") or "",
            "email": partner.email or "",
        }

    def _int_shippo_from_partner(self):
        self.ensure_one()
        return self.picking_type_id.warehouse_id.partner_id or self.company_id.partner_id

    def _int_shippo_product_weight_lb(self, product, qty):
        tmpl = product.product_tmpl_id
        weight_lbs = tmpl.weight_lbs if "weight_lbs" in tmpl._fields else 0.0
        if not weight_lbs and "x_studio_weight_lbs" in tmpl._fields:
            weight_lbs = tmpl.x_studio_weight_lbs
        if weight_lbs:
            return weight_lbs * qty
        uom = tmpl._get_weight_uom_name_from_ir_config_parameter()
        return _weight_to_lb(tmpl.weight or 0.0, uom) * qty

    def _int_shippo_product_dims_in(self, product):
        tmpl = product.product_tmpl_id
        dim_names = ("length_in", "width_in", "height_in")
        if not all(name in tmpl._fields for name in dim_names):
            dim_names = ("x_studio_length_in", "x_studio_width_in", "x_studio_height_in")
        if all(name in tmpl._fields for name in dim_names):
            length, width, height = (tmpl[name] for name in dim_names)
            if length or width or height:
                return length or 0.0, width or 0.0, height or 0.0
        return 0.0, 0.0, 0.0

    def _int_shippo_move_lines(self):
        self.ensure_one()
        return self.move_ids.filtered(lambda m: m.state != "cancel" and m.product_id.type != "service")

    def _int_shippo_content_weight_lb(self):
        self.ensure_one()
        return sum(
            self._int_shippo_product_weight_lb(move.product_id, move.product_uom_qty)
            for move in self._int_shippo_move_lines()
        )

    def _int_shippo_suggest_box(self):
        self.ensure_one()
        boxes = self.env["int.shippo.box"].search([
            ("length_in", ">", 0),
            ("width_in", ">", 0),
            ("height_in", ">", 0),
        ])
        if not boxes:
            return self.env["int.shippo.box"]
        max_l = max_w = max_h = 0.0
        volume = 0.0
        for move in self._int_shippo_move_lines():
            length, width, height = self._int_shippo_product_dims_in(move.product_id)
            dims = sorted((length, width, height), reverse=True)
            max_l = max(max_l, dims[0])
            max_w = max(max_w, dims[1])
            max_h = max(max_h, dims[2])
            volume += length * width * height * move.product_uom_qty
        weight_lb = self._int_shippo_content_weight_lb()
        fits = []
        for box in boxes:
            length, width, height = box.length_in, box.width_in, box.height_in
            outer = sorted((length, width, height), reverse=True)
            if max_l and (outer[0] + 1e-6 < max_l or outer[1] + 1e-6 < max_w or outer[2] + 1e-6 < max_h):
                continue
            if volume and length * width * height + 1e-6 < volume:
                continue
            if box.max_lb and weight_lb + (box.empty_lb or 0.0) > box.max_lb + 1e-6:
                continue
            fits.append((length * width * height, box))
        if not fits:
            return boxes.sorted(lambda b: b.length_in * b.width_in * b.height_in)[:1]
        fits.sort(key=lambda item: item[0])
        return fits[0][1]

    def _int_shippo_parcels(self, box=None, weight_lb=None, length_in=None, width_in=None, height_in=None):
        self.ensure_one()
        box = box or self.int_shippo_box_id or self._int_shippo_suggest_box()
        if length_in is None or width_in is None or height_in is None:
            if box:
                length_in, width_in, height_in = box.length_in, box.width_in, box.height_in
            else:
                length_in = width_in = height_in = 10.0
        if weight_lb is None:
            weight_lb = self._int_shippo_content_weight_lb()
            if box:
                weight_lb += box.empty_lb or 0.0
        weight_lb = max(weight_lb or 0.1, 0.1)
        return [{
            "length": f"{max(length_in or 1.0, 0.1):.2f}",
            "width": f"{max(width_in or 1.0, 0.1):.2f}",
            "height": f"{max(height_in or 1.0, 0.1):.2f}",
            "distance_unit": "in",
            "weight": f"{weight_lb:.2f}",
            "mass_unit": "lb",
        }]

    @api.model
    def _int_shippo_fallback_parcel(self, order):
        weight = 0.1
        for line in order.order_line.filtered(lambda l: l.product_id.type != "service"):
            weight += self._int_shippo_product_weight_lb(line.product_id, line.product_uom_qty)
        return {
            "length": "10",
            "width": "10",
            "height": "10",
            "distance_unit": "in",
            "weight": f"{max(weight, 0.1):.2f}",
            "mass_unit": "lb",
        }
