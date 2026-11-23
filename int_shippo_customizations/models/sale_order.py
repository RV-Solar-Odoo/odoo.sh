import json
import logging
import math

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Quotes are reused for this long before Shippo is asked again. The cache is also
# keyed on the cart and the delivery address, so any change refetches immediately.
RATE_CACHE_MINUTES = 60

# UPS and FedEx refuse single parcels heavier than this.
PARCEL_MAX_LB = 150.0
# Past this many boxes a shipment is freight, whatever it weighs.
MAX_PARCELS = 20
# Carts heavier than this go freight. Change it under Inventory > Settings > Shippo.
DEFAULT_FREIGHT_OVER_LB = 500.0
DEFAULT_PARCEL_IN = 10.0


class SaleOrder(models.Model):
    _inherit = "sale.order"

    int_shippo_rate_key = fields.Char(copy=False, readonly=True)
    int_shippo_rate_json = fields.Text(copy=False, readonly=True)
    int_shippo_rate_date = fields.Datetime(copy=False, readonly=True)
    int_chosen_carrier_id = fields.Many2one(
        "delivery.carrier",
        copy=False,
        readonly=True,
        help="Delivery method the customer clicked at checkout, as opposed to one checkout picked for them.",
    )

    def _int_shippo_order_lines(self):
        """Lines the website shipping quote covers. Backordered items ship later and are left out."""
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: line.product_id
            and line.product_id.type != "service"
            and not line.display_type
            and not line.is_delivery
            and line._int_shipping_quote_qty() > 0
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

    def _get_preferred_delivery_method(self, available_delivery_methods):
        """Start carts on a shipped method; store pickup stays one click away."""
        delivery_method = super()._get_preferred_delivery_method(available_delivery_methods)
        if (
            delivery_method.delivery_type == "in_store"
            and delivery_method != self.int_chosen_carrier_id
            and delivery_method != self.partner_shipping_id.property_delivery_carrier_id
        ):
            shipped = available_delivery_methods.filtered(lambda dm: dm.delivery_type != "in_store")
            delivery_method = shipped[:1] or delivery_method
        return delivery_method

    def _int_drop_unchosen_pickup(self):
        """Clear store pickup that checkout fell back to while nothing else was offered.

        Checkout keeps the current method whenever its price still matches, and free
        Ground costs the same $0 as pickup, so the fallback would otherwise stick after
        the customer fixes their address.
        """
        self.ensure_one()
        if self.carrier_id.delivery_type == "in_store" and self.carrier_id != self.int_chosen_carrier_id:
            self._remove_delivery_line()
            self.carrier_id = False

    def _int_shipping_unavailable_message(self, delivery_methods):
        """Why checkout offers no shipped method for this address, or False if it offers one.

        Without this the shipped methods just vanish (bad ZIP, foreign address, Shippo
        down) and the customer is left looking at store pickup with no explanation.
        """
        self.ensure_one()
        if not self._has_deliverable_products():
            return False
        if delivery_methods.filtered(lambda dm: dm.delivery_type != "in_store"):
            return False
        partner = self.partner_shipping_id
        if not partner or partner == self.website_id.user_id.partner_id:
            return False
        if not self.env["delivery.carrier"].sudo().search_count([
            ("delivery_type", "!=", "in_store"),
            ("is_published", "=", True),
            ("website_id", "in", (False, self.website_id.id)),
            *self.env["delivery.carrier"]._check_company_domain(self.company_id),
        ], limit=1):
            return False
        home_country = self.warehouse_id.partner_id.country_id or self.company_id.country_id
        if partner.country_id and home_country and partner.country_id != home_country:
            return self.env._(
                "We can't quote shipping to %(country)s online.",
                country=partner.country_id.name,
            )
        return self.env._(
            "We couldn't get shipping rates for this address. Check the street, city, "
            "and ZIP code, then try again."
        )

    def _int_shippo_content_weight_lb(self):
        self.ensure_one()
        picking = self.env["stock.picking"]
        return sum(
            picking._int_shippo_product_weight_lb(line.product_id, line._int_shipping_quote_qty())
            for line in self._int_shippo_order_lines()
        )

    def _int_shippo_suggest_box(self):
        self.ensure_one()
        picking = self.env["stock.picking"]
        items = [
            (*picking._int_shippo_product_dims_in(line.product_id), line._int_shipping_quote_qty())
            for line in self._int_shippo_order_lines()
        ]
        return self.env["int.shippo.box"].suggest_for_items(items, self._int_shippo_content_weight_lb())

    def _int_shippo_units(self):
        """One (weight_lb, (length, width, height)) entry per unit that ships now."""
        self.ensure_one()
        picking = self.env["stock.picking"]
        units = []
        for line in self._int_shippo_order_lines():
            qty = line._int_shipping_quote_qty()
            unit_lb = picking._int_shippo_product_weight_lb(line.product_id, 1.0)
            dims = picking._int_shippo_product_dims_in(line.product_id)
            whole = int(math.floor(qty + 1e-6))
            units.extend([(unit_lb, dims)] * whole)
            if qty - whole > 1e-6:
                units.append((unit_lb * (qty - whole), dims))
        return units

    def _int_shippo_packages(self):
        """Boxes for the website quote: a list of (box, content_lb, dims) tuples.

        The whole cart goes in one box when it fits. Otherwise units are packed
        heaviest first into the largest box, each box kept under its own weight limit
        and the carriers' 150 lb. A unit too big for every box ships on its own in its
        own dimensions. ``box`` is empty for those, and when no boxes are set up.
        """
        self.ensure_one()
        Box = self.env["int.shippo.box"]
        items = [
            (*self.env["stock.picking"]._int_shippo_product_dims_in(line.product_id), line._int_shipping_quote_qty())
            for line in self._int_shippo_order_lines()
        ]
        weight_lb = self._int_shippo_content_weight_lb()
        boxes = Box._int_boxes()
        box = Box.fitting_box_for_items(items, weight_lb)
        if box and weight_lb + (box.empty_lb or 0.0) <= PARCEL_MAX_LB:
            return [(box, weight_lb, None)]
        if not boxes:
            if weight_lb <= PARCEL_MAX_LB:
                return [(Box, weight_lb, None)]
            count = int(math.ceil(weight_lb / PARCEL_MAX_LB))
            return [(Box, weight_lb / count, None)] * count

        largest = boxes.sorted(lambda b: b.length_in * b.width_in * b.height_in)[-1]
        capacity_lb = min((largest.max_lb or PARCEL_MAX_LB) - (largest.empty_lb or 0.0), PARCEL_MAX_LB)
        capacity_in3 = largest.length_in * largest.width_in * largest.height_in
        packages = []
        bins = []  # [content_lb, volume_in3, [items]]
        fits_a_box = {}
        for unit_lb, dims in sorted(self._int_shippo_units(), key=lambda unit: unit[0], reverse=True):
            volume = dims[0] * dims[1] * dims[2]
            if (unit_lb, dims) not in fits_a_box:
                fits_a_box[unit_lb, dims] = bool(Box.fitting_box_for_items([(*dims, 1.0)], unit_lb))
            if not fits_a_box[unit_lb, dims]:
                packages.append((Box, unit_lb, dims if volume else None))
                continue
            for current in bins:
                if current[0] + unit_lb <= capacity_lb + 1e-6 and current[1] + volume <= capacity_in3 + 1e-6:
                    current[0] += unit_lb
                    current[1] += volume
                    current[2].append((*dims, 1.0))
                    break
            else:
                bins.append([unit_lb, volume, [(*dims, 1.0)]])
        for content_lb, _volume, bin_items in bins:
            packages.append((Box.fitting_box_for_items(bin_items, content_lb) or largest, content_lb, None))
        return packages

    def _int_shippo_parcels(self):
        self.ensure_one()
        parcels = []
        for box, content_lb, dims in self._int_shippo_packages():
            weight_lb = content_lb
            if box:
                weight_lb += box.empty_lb or 0.0
                length_in, width_in, height_in = box.length_in, box.width_in, box.height_in
            elif dims:
                length_in, width_in, height_in = dims
            else:
                length_in = width_in = height_in = DEFAULT_PARCEL_IN
            weight_lb = max(weight_lb or 0.1, 0.1)
            parcels.append({
                "length": f"{max(length_in or 1.0, 0.1):.2f}",
                "width": f"{max(width_in or 1.0, 0.1):.2f}",
                "height": f"{max(height_in or 1.0, 0.1):.2f}",
                "distance_unit": "in",
                "weight": f"{weight_lb:.2f}",
                "mass_unit": "lb",
            })
        return parcels

    def _int_freight_over_lb(self):
        value = self.env["ir.config_parameter"].sudo().get_param("int_shippo.freight_over_lb")
        try:
            return float(value) if value not in (None, False, "") else DEFAULT_FREIGHT_OVER_LB
        except ValueError:
            return DEFAULT_FREIGHT_OVER_LB

    def _int_shippo_needs_freight(self):
        """Too heavy or too big for parcel carriers, so checkout offers freight."""
        self.ensure_one()
        if not self._int_shippo_order_lines():
            return False
        limit = self._int_freight_over_lb()
        if limit > 0 and self._int_shippo_content_weight_lb() > limit + 1e-6:
            return True
        packages = self._int_shippo_packages()
        if len(packages) > MAX_PARCELS:
            return True
        return any(
            content_lb + ((box.empty_lb or 0.0) if box else 0.0) > PARCEL_MAX_LB + 1e-6
            for box, content_lb, _dims in packages
        )

    def _int_nothing_ships_now(self):
        """Every product in the cart is backordered, so there is nothing to ship yet."""
        self.ensure_one()
        goods = self.order_line.filtered(
            lambda line: line.product_id
            and line.product_id.type != "service"
            and not line.display_type
            and not line.is_delivery
            and line.product_uom_qty
        )
        return bool(goods) and not self._int_shippo_order_lines()

    def _int_website_checkout_cart(self):
        return bool(self.website_id) and self.state in ("draft", "sent")

    def action_confirm(self):
        res = super().action_confirm()
        for order in self.filtered(lambda o: o.carrier_id.int_checkout_role == "freight"):
            order.message_post(
                body=self.env._("Freight order: quote the freight and add the charge before it ships."),
                subtype_xmlid="mail.mt_note",
            )
            if order.user_id:
                order.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=self.env._("Quote freight"),
                    user_id=order.user_id.id,
                )
        return res

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
                    (line.product_id.id, line._int_shipping_quote_qty())
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

    def _int_shippo_checkout_providers(self):
        """Shippo providers the published checkout methods quote from, casefolded."""
        carriers = self.env["delivery.carrier"].sudo().search([
            ("delivery_type", "=", "shippo"),
            ("is_published", "=", True),
        ])
        return {
            token
            for carrier in carriers
            for token in carrier._int_shippo_service_tokens(carrier.int_shippo_provider)
        }

    def _int_shippo_rate_providers(self, rates):
        return {(rate.get("provider") or "").casefold() for rate in rates or []}

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
        rates = shipment.get("rates") or []
        # Shippo answers SUCCESS even when a carrier refused to quote (throttled,
        # out of service area, bad account); the reason is only in `messages`.
        # A carrier that is simply not connected sends no message at all.
        missing = self._int_shippo_checkout_providers() - self._int_shippo_rate_providers(rates)
        refused = set()
        for message in shipment.get("messages") or []:
            source = (message.get("source") or "").casefold()
            if source in missing:
                refused.add(source)
                _logger.warning(
                    "Shippo returned no %s rates for %s: %s",
                    message.get("source"), self.name, message.get("text"),
                )
        return rates, refused

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
            rates, refused = self._int_shippo_request_rates()
        except UserError:
            request_cache[key] = stored if stored is not None else []
            if stored is not None:
                _logger.warning(
                    "Shippo rate call failed for %s; reusing the last quote for this "
                    "cart and address.", self.name,
                )
                return stored
            raise

        # A carrier dropping out of one answer would hide every method tied to it,
        # so keep the last quote for this cart that still had it.
        lost = (
            self._int_shippo_checkout_providers()
            & self._int_shippo_rate_providers(stored)
        ) - self._int_shippo_rate_providers(rates)
        if stored is not None and lost:
            _logger.warning(
                "Shippo quote for %s came back without %s; reusing the last quote "
                "for this cart and address.", self.name, ", ".join(sorted(lost)),
            )
            request_cache[key] = stored
            return stored

        # Only a real quote is worth keeping for an hour. An empty answer is still
        # shared across this render, but the next page load asks Shippo again. A
        # quote a carrier refused is kept as a fallback but never counts as fresh.
        if rates:
            self.sudo().write({
                "int_shippo_rate_key": key,
                "int_shippo_rate_json": json.dumps(rates),
                "int_shippo_rate_date": False if refused else fields.Datetime.now(),
            })
        request_cache[key] = rates
        return rates


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _int_shipping_quote_qty(self):
        """Quantity the website shipping quote is for, in the line's unit.

        Sales Customizations lowers it for backordered items, which ship later and are
        charged shipping then.
        """
        self.ensure_one()
        return self.product_uom_qty
