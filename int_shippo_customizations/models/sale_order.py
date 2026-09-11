import json
import logging

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Quotes are reused for this long before Shippo is asked again. The cache is also
# keyed on the cart and the delivery address, so any change refetches immediately.
RATE_CACHE_MINUTES = 60


class SaleOrder(models.Model):
    _inherit = "sale.order"

    int_shippo_rate_key = fields.Char(copy=False, readonly=True)
    int_shippo_rate_json = fields.Text(copy=False, readonly=True)
    int_shippo_rate_date = fields.Datetime(copy=False, readonly=True)

    def _int_shippo_order_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: line.product_id
            and line.product_id.type != "service"
            and not line.display_type
            and not line.is_delivery
        )

    def _int_order_product_categories(self):
        self.ensure_one()
        return self._int_shippo_order_lines().product_id.categ_id

    def _int_ancestor_categories(self, categories):
        seen = self.env["product.category"]
        for category in categories:
            current = category
            while current and current not in seen:
                seen |= current
                current = current.parent_id
        return seen

    def _int_requires_ground_shipping(self):
        self.ensure_one()
        categories = self._int_ancestor_categories(self._int_order_product_categories())
        return any(getattr(category, "ground_shipping_only", False) for category in categories)

    def _int_shipping_upcharge(self):
        self.ensure_one()
        categories = self._int_ancestor_categories(self._int_order_product_categories())
        if not categories:
            return 0.0
        return max(getattr(category, "shipping_upcharge", 0.0) or 0.0 for category in categories)

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

    def _int_shippo_rate_key(self):
        """Fingerprint of everything Shippo prices on, so any change refetches."""
        self.ensure_one()
        partner = self.partner_shipping_id or self.partner_id
        return json.dumps(
            {
                "street": partner.street,
                "street2": partner.street2,
                "city": partner.city,
                "zip": partner.zip,
                "state": partner.state_id.id,
                "country": partner.country_id.id,
                "warehouse": self.warehouse_id.id,
                "parcels": self._int_shippo_parcels(),
                "lines": sorted(
                    (line.product_id.id, line.product_uom_qty)
                    for line in self._int_shippo_order_lines()
                ),
            },
            sort_keys=True,
            default=str,
        )

    def _int_shippo_stored_rates(self, key):
        self.ensure_one()
        if self.int_shippo_rate_key != key or not self.int_shippo_rate_json:
            return None
        try:
            return json.loads(self.int_shippo_rate_json)
        except ValueError:
            return None

    def _int_shippo_stored_rates_are_fresh(self):
        self.ensure_one()
        if not self.int_shippo_rate_date:
            return False
        age = fields.Datetime.now() - self.int_shippo_rate_date
        return age.total_seconds() < RATE_CACHE_MINUTES * 60

    def _int_shippo_request_rates(self):
        self.ensure_one()
        from_partner = self.warehouse_id.partner_id or self.company_id.partner_id
        to_partner = self.partner_shipping_id or self.partner_id
        picking = self.env["stock.picking"]
        shipment = self.env["int.shippo.api"].request(
            "POST",
            "/shipments/",
            {
                "address_from": picking._int_shippo_address(from_partner),
                "address_to": picking._int_shippo_address(to_partner),
                "parcels": self._int_shippo_parcels(),
                "async": False,
            },
            # Checkout renders synchronously, so fail fast rather than hang the page.
            timeout=20,
            retries=1,
        )
        return shipment.get("rates") or []

    def _int_shippo_fetch_rates(self):
        self.ensure_one()
        key = self._int_shippo_rate_key()

        # Within one render every carrier asks for rates, so answer them all from
        # a single call — including when that call failed.
        request_cache = getattr(self.env.cr, "_int_shippo_rates", None)
        if request_cache is None:
            request_cache = {}
            self.env.cr._int_shippo_rates = request_cache
        if key in request_cache:
            return request_cache[key]

        stored = self._int_shippo_stored_rates(key)
        if stored is not None and self._int_shippo_stored_rates_are_fresh():
            request_cache[key] = stored
            return stored

        try:
            rates = self._int_shippo_request_rates()
        except UserError:
            request_cache[key] = stored if stored is not None else []
            if stored is not None:
                _logger.warning(
                    "Shippo rate call failed for %s; reusing the last quote for this "
                    "cart and address.", self.name,
                )
                return stored
            raise

        # Only a real quote is worth keeping for an hour. An empty answer is still
        # shared across this render, but the next page load asks Shippo again.
        if rates:
            self.sudo().write({
                "int_shippo_rate_key": key,
                "int_shippo_rate_json": json.dumps(rates),
                "int_shippo_rate_date": fields.Datetime.now(),
            })
        request_cache[key] = rates
        return rates
