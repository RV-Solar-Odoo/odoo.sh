from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    int_ship_location_type = fields.Selection(
        [("commercial", "Commercial"), ("residential", "Residential")],
        string="Location type",
        copy=False,
    )
    int_ship_has_dock = fields.Boolean(string="Loading dock", copy=False)
    int_ship_has_forklift = fields.Boolean(string="Forklift on site", copy=False)
    int_ship_details_set = fields.Boolean(copy=False)
    int_liftgate_needed = fields.Boolean(
        string="Liftgate required",
        compute="_compute_int_liftgate_needed",
        store=True,
    )

    @api.depends("int_ship_location_type", "int_ship_has_dock", "int_ship_has_forklift")
    def _compute_int_liftgate_needed(self):
        for picking in self:
            residential = picking.int_ship_location_type == "residential"
            bare_commercial = (
                picking.int_ship_location_type == "commercial"
                and not picking.int_ship_has_dock
                and not picking.int_ship_has_forklift
            )
            picking.int_liftgate_needed = residential or bare_commercial

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        pickings._int_snapshot_shipping()
        return pickings

    def write(self, vals):
        result = super().write(vals)
        if "sale_id" in vals or "partner_id" in vals:
            self.filtered(lambda picking: not picking.int_ship_details_set)._int_snapshot_shipping()
        return result

    def _int_snapshot_shipping(self):
        """Copy the ship-to details once. Later address edits do not change the slip."""
        for picking in self:
            partner = picking.sale_id.partner_shipping_id or picking.partner_id
            if not partner or "int_location_type" not in partner._fields:
                continue
            picking.write({
                "int_ship_location_type": partner.int_location_type or False,
                "int_ship_has_dock": bool(partner.int_has_loading_dock),
                "int_ship_has_forklift": bool(partner.int_has_forklift),
                "int_ship_details_set": True,
            })

    @api.model
    def _int_portal_backorder_moves(self, commercial):
        """Open outgoing lines for orders that already shipped something."""
        if not self.env["sale.order"]._int_portal_commercial_allowed(commercial):
            return self.env["stock.move"]
        pickings = self.sudo().search([
            ("picking_type_code", "=", "outgoing"),
            ("state", "not in", ("done", "cancel")),
            ("sale_id.partner_id", "child_of", commercial.id),
        ])
        moves = self.env["stock.move"]
        for picking in pickings:
            order = picking.sale_id
            shipped = order.picking_ids.filtered(
                lambda other: other.picking_type_code == "outgoing" and other.state == "done"
            )
            if not picking.backorder_id and not shipped:
                continue
            moves |= picking.move_ids.filtered(
                lambda move: move.state not in ("done", "cancel") and move.product_uom_qty > 0
            )
        return moves

    def _int_portal_tracking_links(self):
        """Tracking numbers on this shipment, each with a link when one exists.

        Several numbers in one reference are split. A link is kept only when it
        belongs to a single number. A missing link leaves the number as text.
        """
        self.ensure_one()
        multiple = self._int_portal_multiple_tracking()
        if multiple:
            return multiple
        ref = (self.carrier_tracking_ref or "").strip()
        if not ref:
            return []
        parts = [part.strip() for part in ref.split(",") if part.strip()]
        url = self.carrier_tracking_url or ""
        if len(parts) == 1 and self._int_portal_http_url(url):
            return [{"number": parts[0], "url": url}]
        return [{"number": part, "url": False} for part in parts]

    def _int_portal_multiple_tracking(self):
        if not hasattr(self, "get_multiple_carrier_tracking"):
            return []
        parsed = self.get_multiple_carrier_tracking()
        if not isinstance(parsed, (list, tuple)):
            return []
        links = []
        for line in parsed:
            number = False
            url = False
            if isinstance(line, (list, tuple)) and line:
                number = str(line[0] or "").strip()
                url = line[1] if len(line) > 1 else False
            elif isinstance(line, dict):
                number = str(line.get("tracking_number") or line.get("name") or "").strip()
                url = line.get("url")
            if not number:
                continue
            links.append({
                "number": number,
                "url": url if self._int_portal_http_url(url) else False,
            })
        return links

    @staticmethod
    def _int_portal_http_url(url):
        return isinstance(url, str) and url.startswith(("http://", "https://"))
