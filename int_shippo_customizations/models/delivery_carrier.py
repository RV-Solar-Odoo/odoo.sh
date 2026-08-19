from odoo import fields, models
from odoo.exceptions import UserError


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("shippo", "Shippo")],
        ondelete={"shippo": "set default"},
    )

    def shippo_rate_shipment(self, order):
        self.ensure_one()
        picking = order.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing")[:1]
        try:
            parcels = (picking._int_shippo_parcels() if picking
                       else order._int_shippo_parcels() if hasattr(order, "_int_shippo_parcels")
                       else [])
            if not parcels:
                parcels = [self.env["stock.picking"]._int_shippo_fallback_parcel(order)]
            shipment = self.env["int.shippo.api"].request("POST", "/shipments/", {
                "address_from": self.env["stock.picking"]._int_shippo_address(order.warehouse_id.partner_id or order.company_id.partner_id),
                "address_to": self.env["stock.picking"]._int_shippo_address(order.partner_shipping_id or order.partner_id),
                "parcels": parcels,
                "async": False,
            })
            amounts = [float(rate["amount"]) for rate in shipment.get("rates") or [] if rate.get("amount")]
            if not amounts:
                messages = shipment.get("messages") or []
                text = "; ".join(m.get("text", "") for m in messages if m.get("text"))
                return {
                    "success": False,
                    "price": 0.0,
                    "error_message": text or self.env._("Shippo returned no rates."),
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
