from odoo import fields, models
from odoo.exceptions import UserError


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("shippo", "Shippo")],
        ondelete={"shippo": "set default"},
    )
    int_shippo_provider = fields.Char(
        string="Shippo carrier",
        help="If set, checkout uses the cheapest Shippo rate from this provider (UPS, USPS, FedEx).",
    )

    def shippo_rate_shipment(self, order):
        self.ensure_one()
        try:
            if order._name == "sale.order":
                rates = order._int_shippo_fetch_rates()
            else:
                rates = self._int_shippo_rates_from_picking(order)
            if self.int_shippo_provider:
                provider = self.int_shippo_provider.casefold()
                rates = [
                    rate for rate in rates
                    if (rate.get("provider") or "").casefold() == provider
                ]
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
                "price": min(amounts),
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
