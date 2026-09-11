from odoo import fields, models
from odoo.exceptions import UserError


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("shippo", "Shippo")],
        ondelete={"shippo": "set default"},
    )
    int_shippo_provider = fields.Char(
        string="Shippo carriers",
        help="Comma-separated Shippo providers this method may quote from (e.g. UPS,FedEx). "
             "Checkout uses the cheapest matching rate across them. Empty means any provider.",
    )
    int_shippo_service_include = fields.Char(
        string="Shippo service includes",
        help="Comma-separated tokens that must appear in the Shippo service name or token "
             "(e.g. ground, 2nd day, next day).",
    )
    int_shippo_service_exclude = fields.Char(
        string="Shippo service excludes",
        help="Comma-separated tokens that exclude an otherwise matching Shippo service "
             "(e.g. saver, so Ground does not also match Ground Saver).",
    )
    int_free_over_amount = fields.Float(
        string="Free over",
        help="If the order total without shipping is at least this amount, checkout quotes $0 "
             "for this method. Faster methods are unchanged.",
    )

    def _int_is_ground_method(self):
        includes = self._int_shippo_service_tokens(self.int_shippo_service_include)
        return "ground" in includes and "saver" not in " ".join(includes)

    def _is_available_for_order(self, order):
        if not super()._is_available_for_order(order):
            return False
        if (
            order._name == "sale.order"
            and order._int_requires_ground_shipping()
            and not self._int_is_ground_method()
        ):
            return False
        if self.delivery_type != "shippo":
            return True
        if not self.int_shippo_provider and not self.int_shippo_service_include:
            return True
        return bool(self.rate_shipment(order).get("success"))

    def _int_shippo_service_tokens(self, value):
        return [token.strip().casefold() for token in (value or "").split(",") if token.strip()]

    def _int_shippo_service_text(self, rate):
        sl = rate.get("servicelevel") or {}
        parts = [rate.get("provider"), rate.get("servicelevel_name")]
        if isinstance(sl, dict):
            parts.extend([sl.get("name"), sl.get("token"), sl.get("terms")])
        else:
            parts.append(sl)
        return " ".join(str(part) for part in parts if part).replace("_", " ").casefold()

    def _int_shippo_rate_matches(self, rate):
        providers = self._int_shippo_service_tokens(self.int_shippo_provider)
        if providers and (rate.get("provider") or "").casefold() not in providers:
            return False
        text = self._int_shippo_service_text(rate)
        includes = self._int_shippo_service_tokens(self.int_shippo_service_include)
        excludes = self._int_shippo_service_tokens(self.int_shippo_service_exclude)
        if includes and not any(token in text for token in includes):
            return False
        if excludes and any(token in text for token in excludes):
            return False
        return True

    def _int_shippo_matching_rates(self, rates):
        return [rate for rate in rates if self._int_shippo_rate_matches(rate)]

    def _int_order_amount_without_delivery(self, order):
        if order._name != "sale.order":
            return 0.0
        if hasattr(order, "_compute_amount_total_without_delivery"):
            return order._compute_amount_total_without_delivery()
        delivery_total = sum(order.order_line.filtered("is_delivery").mapped("price_total"))
        return order.amount_total - delivery_total

    def _int_shippo_checkout_price(self, order, price):
        if (
            order._name == "sale.order"
            and self.int_free_over_amount
            and self._int_order_amount_without_delivery(order) + 1e-6 >= self.int_free_over_amount
        ):
            price = 0.0
        if order._name == "sale.order":
            price += order._int_shipping_upcharge()
        return price

    def shippo_rate_shipment(self, order):
        self.ensure_one()
        try:
            if order._name == "sale.order":
                rates = order._int_shippo_fetch_rates()
            else:
                rates = self._int_shippo_rates_from_picking(order)
            rates = self._int_shippo_matching_rates(rates)
            amounts = [float(rate["amount"]) for rate in rates if rate.get("amount")]
            if not amounts:
                return {
                    "success": False,
                    "price": 0.0,
                    "error_message": self.env._("Shippo returned no rates for this address and parcel."),
                    "warning_message": False,
                }
            return {
                "success": True,
                "price": self._int_shippo_checkout_price(order, min(amounts)),
                "error_message": False,
                "warning_message": False,
            }
        except UserError as exc:
            return {"success": False, "price": 0.0, "error_message": exc.args[0], "warning_message": False}

    def _int_shippo_rates_from_picking(self, picking):
        if picking._name != "stock.picking":
            picking = picking.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing")[:1]
            if picking:
                parcels = picking._int_shippo_parcels()
                shipment = self.env["int.shippo.api"].request("POST", "/shipments/", {
                    "address_from": picking._int_shippo_address(picking._int_shippo_from_partner()),
                    "address_to": picking._int_shippo_address(picking.partner_id),
                    "parcels": parcels,
                    "async": False,
                })
                return shipment.get("rates") or []
            return []
        shipment = self.env["int.shippo.api"].request("POST", "/shipments/", {
            "address_from": picking._int_shippo_address(picking._int_shippo_from_partner()),
            "address_to": picking._int_shippo_address(picking.partner_id),
            "parcels": picking._int_shippo_parcels(),
            "async": False,
        })
        return shipment.get("rates") or []

    def shippo_send_shipping(self, pickings):
        result = []
        for picking in pickings:
            if not picking.carrier_tracking_ref:
                raise UserError(self.env._(
                    "Buy a Shippo label with Get Shippo Rates before validating %(picking)s.",
                    picking=picking.name,
                ))
            result.append({
                "exact_price": picking.carrier_price or 0.0,
                "tracking_number": picking.carrier_tracking_ref,
            })
        return result

    def shippo_get_tracking_link(self, picking):
        if picking.int_shippo_tracking_url:
            return picking.int_shippo_tracking_url
        if picking.carrier_tracking_ref:
            return f"https://apps.goshippo.com/tracking/{picking.carrier_tracking_ref}"
        return False

    def shippo_cancel_shipment(self, picking):
        picking.ensure_one()
        picking.write({
            "carrier_tracking_ref": False,
            "int_shippo_shipment_id": False,
            "int_shippo_transaction_id": False,
            "int_shippo_label_url": False,
            "int_shippo_tracking_url": False,
            "int_shippo_carrier_name": False,
        })
