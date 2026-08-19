import base64
import urllib.request

from odoo import api, fields, models
from odoo.exceptions import UserError


class ShippoRateWizard(models.TransientModel):
    _name = "int.shippo.rate.wizard"
    _description = "Shippo rate picker"

    picking_id = fields.Many2one("stock.picking", required=True, ondelete="cascade")
    box_id = fields.Many2one("int.shippo.box", string="Box")
    weight_lb = fields.Float(string="Weight (lb)", digits=(16, 2))
    length_in = fields.Float(string="Length (in)", digits=(16, 2))
    width_in = fields.Float(string="Width (in)", digits=(16, 2))
    height_in = fields.Float(string="Height (in)", digits=(16, 2))
    shippo_shipment_id = fields.Char()
    line_ids = fields.One2many("int.shippo.rate.line", "wizard_id", string="Rates")
    selected_line_id = fields.Many2one("int.shippo.rate.line", string="Selected Rate")

    @api.onchange("box_id")
    def _onchange_box_id(self):
        if self.box_id and self.picking_id:
            self.length_in = self.box_id.length_in
            self.width_in = self.box_id.width_in
            self.height_in = self.box_id.height_in
            self.weight_lb = self.picking_id._int_shippo_content_weight_lb() + (self.box_id.empty_lb or 0.0)

    def action_refresh_dims(self):
        self.ensure_one()
        picking = self.picking_id
        if not self.box_id:
            self.box_id = picking._int_shippo_suggest_box()
        if self.box_id:
            self.length_in = self.box_id.length_in
            self.width_in = self.box_id.width_in
            self.height_in = self.box_id.height_in
            self.weight_lb = picking._int_shippo_content_weight_lb() + (self.box_id.empty_lb or 0.0)
        else:
            self.weight_lb = picking._int_shippo_content_weight_lb() or 0.1
            self.length_in = self.width_in = self.height_in = 10.0
        return True

    def action_get_rates(self):
        self.ensure_one()
        picking = self.picking_id
        picking.int_shippo_box_id = self.box_id
        parcels = picking._int_shippo_parcels(
            box=self.box_id,
            weight_lb=self.weight_lb,
            length_in=self.length_in,
            width_in=self.width_in,
            height_in=self.height_in,
        )
        shipment = self.env["int.shippo.api"].request("POST", "/shipments/", {
            "address_from": picking._int_shippo_address(picking._int_shippo_from_partner()),
            "address_to": picking._int_shippo_address(picking.partner_id),
            "parcels": parcels,
            "async": False,
        })
        rates = shipment.get("rates") or []
        if not rates:
            messages = shipment.get("messages") or []
            text = "; ".join(m.get("text", "") for m in messages if m.get("text"))
            raise UserError(text or self.env._("Shippo returned no rates for this address and parcel."))
        self.shippo_shipment_id = shipment.get("object_id")
        self.line_ids.unlink()
        lines = []
        for rate in rates:
            servicelevel = rate.get("servicelevel") or {}
            if isinstance(servicelevel, dict):
                service = servicelevel.get("name")
            else:
                service = servicelevel
            lines.append({
                "wizard_id": self.id,
                "rate_object_id": rate.get("object_id"),
                "carrier": rate.get("provider"),
                "service": service or rate.get("servicelevel_name"),
                "amount": float(rate.get("amount") or 0.0),
                "currency": rate.get("currency"),
                "days": rate.get("estimated_days") or 0,
            })
        created = self.env["int.shippo.rate.line"].create(lines)
        first = created.sorted(lambda line: (line.amount, line.id))[:1]
        if first:
            first.selected = True
            self.selected_line_id = first
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_buy_label(self):
        self.ensure_one()
        if not self.selected_line_id:
            raise UserError(self.env._("Select a Shippo rate first."))
        if not self.selected_line_id.rate_object_id:
            raise UserError(self.env._("This rate is missing a Shippo id. Get rates again."))
        transaction = self.env["int.shippo.api"].request("POST", "/transactions/", {
            "rate": self.selected_line_id.rate_object_id,
            "label_file_type": "PDF",
            "async": False,
        })
        if transaction.get("status") not in ("SUCCESS", "QUEUED"):
            messages = transaction.get("messages") or []
            text = "; ".join(
                m.get("text", str(m)) if isinstance(m, dict) else str(m)
                for m in messages
            )
            raise UserError(text or self.env._("Shippo did not purchase the label."))
        picking = self.picking_id
        tracking = transaction.get("tracking_number")
        label_url = transaction.get("label_url")
        tracking_url = transaction.get("tracking_url_provider")
        shippo_carrier = self.env.ref(
            "int_shippo_customizations.delivery_carrier_shippo",
            raise_if_not_found=False,
        )
        vals = {
            "int_shippo_shipment_id": self.shippo_shipment_id,
            "int_shippo_transaction_id": transaction.get("object_id"),
            "int_shippo_label_url": label_url,
            "int_shippo_tracking_url": tracking_url,
            "int_shippo_box_id": self.box_id.id,
            "int_shippo_carrier_name": " — ".join(
                part for part in (self.selected_line_id.carrier, self.selected_line_id.service) if part
            ),
            "carrier_tracking_ref": tracking,
            "carrier_price": self.selected_line_id.amount,
        }
        if shippo_carrier:
            vals["carrier_id"] = shippo_carrier.id
        picking.write(vals)
        if label_url:
            self._attach_label(picking, label_url, tracking)
        picking.message_post(body=self.env._(
            "Shippo label purchased: %(carrier)s %(service)s — %(amount).2f %(currency)s. Tracking %(tracking)s",
            carrier=self.selected_line_id.carrier,
            service=self.selected_line_id.service,
            amount=self.selected_line_id.amount,
            currency=self.selected_line_id.currency or "",
            tracking=tracking or self.env._("pending"),
        ))
        if label_url:
            return {
                "type": "ir.actions.act_url",
                "url": label_url,
                "target": "new",
            }
        return {"type": "ir.actions.act_window_close"}

    def _attach_label(self, picking, label_url, tracking):
        try:
            with urllib.request.urlopen(label_url, timeout=60) as resp:
                pdf = resp.read()
        except Exception as exc:  # noqa: BLE001 — still keep the purchased label URL
            picking.message_post(body=self.env._(
                "Label purchased but the PDF could not be downloaded (%s). Use the Shipping Label button on the delivery.",
                exc,
            ))
            return
        self.env["ir.attachment"].create({
            "name": f"Shippo Label {tracking or picking.name}.pdf",
            "type": "binary",
            "datas": base64.b64encode(pdf),
            "res_model": "stock.picking",
            "res_id": picking.id,
            "mimetype": "application/pdf",
        })


class ShippoRateLine(models.TransientModel):
    _name = "int.shippo.rate.line"
    _description = "Shippo rate line"
    _order = "amount, id"

    wizard_id = fields.Many2one("int.shippo.rate.wizard", required=True, ondelete="cascade")
    rate_object_id = fields.Char()
    carrier = fields.Char()
    service = fields.Char()
    amount = fields.Float(digits=(16, 2))
    currency = fields.Char()
    days = fields.Integer(string="Est. days")
    selected = fields.Boolean(string="Selected")

    @api.depends("carrier", "service", "amount", "currency", "days")
    def _compute_display_name(self):
        for line in self:
            name = " ".join(part for part in (line.carrier, line.service) if part) or self.env._("Shippo rate")
            price = f"{line.amount:.2f}"
            if line.currency:
                price = f"{price} {line.currency}"
            if line.days:
                line.display_name = f"{name} — {price} ({line.days}d)"
            else:
                line.display_name = f"{name} — {price}"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines.filtered("selected"):
            line.wizard_id.selected_line_id = line
        return lines

    def write(self, vals):
        res = super().write(vals)
        if vals.get("selected"):
            for line in self:
                others = (line.wizard_id.line_ids - line).filtered("selected")
                if others:
                    super(ShippoRateLine, others).write({"selected": False})
                line.wizard_id.selected_line_id = line
        return res

    def action_select(self):
        self.ensure_one()
        self.selected = True
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Shippo Rates"),
            "res_model": self.wizard_id._name,
            "res_id": self.wizard_id.id,
            "view_mode": "form",
            "views": [[False, "form"]],
            "target": "new",
        }
