from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _int_shippo_order_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: line.product_id
            and line.product_id.type != "service"
            and not line.display_type
            and not line.is_delivery
        )

    def _int_shippo_content_weight_lb(self):
        self.ensure_one()
        picking = self.env["stock.picking"]
        return sum(
            picking._int_shippo_product_weight_lb(line.product_id, line.product_uom_qty)
            for line in self._int_shippo_order_lines()
        )

    def _int_shippo_suggest_box(self):
        self.ensure_one()
        picking = self.env["stock.picking"]
        items = [
            (*picking._int_shippo_product_dims_in(line.product_id), line.product_uom_qty)
            for line in self._int_shippo_order_lines()
        ]
        return self.env["int.shippo.box"].suggest_for_items(items, self._int_shippo_content_weight_lb())

    def _int_shippo_parcels(self):
        self.ensure_one()
        box = self._int_shippo_suggest_box()
        weight_lb = self._int_shippo_content_weight_lb()
        if box:
            weight_lb += box.empty_lb or 0.0
            length_in, width_in, height_in = box.length_in, box.width_in, box.height_in
        else:
            length_in = width_in = height_in = 10.0
        weight_lb = max(weight_lb or 0.1, 0.1)
        return [{
            "length": f"{max(length_in or 1.0, 0.1):.2f}",
            "width": f"{max(width_in or 1.0, 0.1):.2f}",
            "height": f"{max(height_in or 1.0, 0.1):.2f}",
            "distance_unit": "in",
            "weight": f"{weight_lb:.2f}",
            "mass_unit": "lb",
        }]

    def _int_shippo_fetch_rates(self):
        self.ensure_one()
        cache = getattr(self.env.cr, "_int_shippo_rates", None)
        if cache is None:
            cache = {}
            self.env.cr._int_shippo_rates = cache
        cache_key = (
            self.id,
            self.partner_shipping_id.id or 0,
            self.warehouse_id.id or 0,
            tuple((line.product_id.id, line.product_uom_qty) for line in self._int_shippo_order_lines()),
        )
        if cache_key in cache:
            return cache[cache_key]
        from_partner = self.warehouse_id.partner_id or self.company_id.partner_id
        to_partner = self.partner_shipping_id or self.partner_id
        picking = self.env["stock.picking"]
        shipment = self.env["int.shippo.api"].request("POST", "/shipments/", {
            "address_from": picking._int_shippo_address(from_partner),
            "address_to": picking._int_shippo_address(to_partner),
            "parcels": self._int_shippo_parcels(),
            "async": False,
        })
        rates = shipment.get("rates") or []
        cache[cache_key] = rates
        return rates
