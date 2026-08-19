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
    int_shippo_package_type_id = fields.Many2one(
        "stock.package.type",
        string="Shippo Box",
        help="Standard carton used for this shipment. Suggested from product dimensions; warehouse can change it.",
    )

    def action_open_shippo_rates(self):
        self.ensure_one()
        if not self.int_shippo_package_type_id:
            self.int_shippo_package_type_id = self._int_shippo_suggest_package_type()
        wizard = self.env["int.shippo.rate.wizard"].create({
            "picking_id": self.id,
            "package_type_id": self.int_shippo_package_type_id.id,
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
            "phone": partner.phone or partner.mobile or "",
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

    def _int_shippo_package_dims_in(self, package_type):
        uom = package_type.length_uom_name
        return (
            _length_to_inches(package_type.packaging_length or 0.0, uom),
            _length_to_inches(package_type.width or 0.0, uom),
            _length_to_inches(package_type.height or 0.0, uom),
        )

    def _int_shippo_package_empty_lb(self, package_type):
        return _weight_to_lb(package_type.base_weight or 0.0, package_type.weight_uom_name)

    def _int_shippo_suggest_package_type(self):
        self.ensure_one()
        types = self.env["stock.package.type"].search([
            ("package_use", "=", "disposable"),
            ("packaging_length", ">", 0),
            ("width", ">", 0),
            ("height", ">", 0),
        ])
        if not types:
            return self.env["stock.package.type"]
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
        for package in types:
            length, width, height = self._int_shippo_package_dims_in(package)
            box = sorted((length, width, height), reverse=True)
            max_lb = _weight_to_lb(package.max_weight or 0.0, package.weight_uom_name)
            if max_l and (box[0] + 1e-6 < max_l or box[1] + 1e-6 < max_w or box[2] + 1e-6 < max_h):
                continue
            if volume and length * width * height + 1e-6 < volume:
                continue
            if max_lb and weight_lb + self._int_shippo_package_empty_lb(package) > max_lb + 1e-6:
                continue
            fits.append((length * width * height, package))
        if not fits:
            return types.sorted(lambda p: p.packaging_length * p.width * p.height)[:1]
        fits.sort(key=lambda item: item[0])
        return fits[0][1]

    def _int_shippo_parcels(self, package_type=None, weight_lb=None, length_in=None, width_in=None, height_in=None):
        self.ensure_one()
        package_type = package_type or self.int_shippo_package_type_id or self._int_shippo_suggest_package_type()
        if length_in is None or width_in is None or height_in is None:
            if package_type:
                length_in, width_in, height_in = self._int_shippo_package_dims_in(package_type)
            else:
                length_in = width_in = height_in = 10.0
        if weight_lb is None:
            weight_lb = self._int_shippo_content_weight_lb()
            if package_type:
                weight_lb += self._int_shippo_package_empty_lb(package_type)
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
