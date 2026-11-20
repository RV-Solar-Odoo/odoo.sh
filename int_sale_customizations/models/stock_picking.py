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

    @api.model
    def _int_portal_delivery_domain(self, commercial, filterby="all"):
        """Picks and outgoing shipments for this commercial partner.

        Done, open, and backordered transfers are included. Vendor receipts and
        cancelled transfers are left out. The domain is safe to run with sudo.
        """
        if not self.env["sale.order"]._int_portal_commercial_allowed(commercial):
            return [("id", "=", 0)]
        domain = [
            ("picking_type_code", "in", ("outgoing", "internal", "dropship")),
            ("state", "!=", "cancel"),
            ("sale_id.partner_id", "child_of", commercial.id),
        ]
        if filterby == "shipped":
            domain += [("state", "=", "done"), ("picking_type_code", "=", "outgoing")]
        elif filterby == "open":
            domain.append(("state", "not in", ("done", "cancel")))
        elif filterby == "backordered":
            domain += [
                ("backorder_id", "!=", False),
                ("state", "not in", ("done", "cancel")),
            ]
        return domain

    def _int_portal_owned_delivery(self, user, picking_id):
        """One delivery this user may open, or an empty record."""
        if not user or not user.int_portal_can("view_orders"):
            return self.browse()
        commercial = user.partner_id.commercial_partner_id
        return self.sudo().search(
            self._int_portal_delivery_domain(commercial) + [("id", "=", picking_id)],
            limit=1,
        )

    def _int_portal_downstream_shipments(self):
        """Delivery orders this transfer feeds, following the move chain.

        Portal users cannot read stock moves. The caller has already limited
        this to one of their shipments.
        """
        self.ensure_one()
        picking = self.sudo()
        dest = picking.move_ids.move_dest_ids
        seen = picking.env["stock.move"]
        shipments = picking.env["stock.picking"]
        while dest:
            dest = dest - seen
            if not dest:
                break
            seen |= dest
            shipments |= dest.picking_id.filtered(
                lambda picking: picking.picking_type_code in ("outgoing", "dropship")
            )
            dest = dest.move_dest_ids
        return shipments

    def _int_portal_upstream_picks(self):
        """Picks that feed this transfer, following the move chain.

        Portal users cannot read stock moves. The caller has already limited
        this to one of their shipments.
        """
        self.ensure_one()
        picking = self.sudo()
        orig = picking.move_ids.move_orig_ids
        seen = picking.env["stock.move"]
        picks = picking.env["stock.picking"]
        while orig:
            orig = orig - seen
            if not orig:
                break
            seen |= orig
            picks |= orig.picking_id.filtered(
                lambda picking: picking.picking_type_code == "internal" and picking.state != "cancel"
            )
            orig = orig.move_orig_ids
        return picks

    def _int_portal_shipment(self):
        """The customer shipment this transfer belongs to.

        A pick that feeds a delivery order is a stage of that delivery order.
        A delivery order, a dropship, or a pick that has not reached shipping
        yet is its own shipment.
        """
        self.ensure_one()
        picking = self.sudo()
        if picking.picking_type_code in ("outgoing", "dropship"):
            return picking
        shipments = picking._int_portal_downstream_shipments().filtered(lambda picking: picking.state != "cancel")
        if not shipments:
            return picking
        open_shipments = shipments.filtered(lambda picking: picking.state != "done")
        return (open_shipments or shipments).sorted("id")[-1]

    def _int_portal_delivery_stages(self):
        """Pick steps, then the shipment, in warehouse order."""
        self.ensure_one()
        shipment = self._int_portal_shipment()
        picks = shipment._int_portal_upstream_picks().sorted("id")
        stages = [pick for pick in picks]
        if shipment not in picks:
            stages.append(shipment)
        return stages

    def _int_portal_step_name(self):
        self.ensure_one()
        if self.picking_type_code == "internal":
            return "Pick"
        return "Shipment"

    def _int_portal_step_state(self):
        self.ensure_one()
        if self.state == "done" and self.picking_type_code == "internal":
            return "Picked"
        if self.state == "done":
            return "Shipped"
        return "In progress"

    @api.model
    def _int_portal_delivery_rows(self, commercial, filterby="all"):
        """One row per customer shipment.

        Picks that feed a delivery order are left out of the list. Their stage
        is shown on that delivery. A pick with no delivery order yet stays, so
        an order still being picked is visible.
        """
        pickings = self.sudo().search(self._int_portal_delivery_domain(commercial))
        pickings.mapped("move_ids.move_dest_ids.picking_id")
        rows = self.sudo().browse()
        for picking in pickings:
            rows |= picking._int_portal_shipment()
        if filterby == "shipped":
            rows = rows.filtered(lambda picking: picking._int_portal_delivery_status()[0] == "shipped")
        elif filterby == "open":
            rows = rows.filtered(lambda picking: picking._int_portal_delivery_status()[0] != "shipped")
        elif filterby == "backordered":
            rows = rows.filtered(lambda picking: picking._int_portal_delivery_status()[0] == "backordered")
        return rows.sorted(
            key=lambda picking: (picking.scheduled_date or picking.create_date, picking.id),
            reverse=True,
        )

    def _int_portal_as_shipments(self):
        """Portal deliveries on an order: one row per customer shipment."""
        visible = self.sudo().filtered(
            lambda picking: picking.state != "cancel" and picking.picking_type_code in ("outgoing", "internal", "dropship")
        )
        visible.mapped("move_ids.move_dest_ids.picking_id")
        rows = self.sudo().browse()
        for picking in visible:
            rows |= picking._int_portal_shipment()
        return rows

    def _int_portal_delivery_status(self):
        """``(code, label, badge class)`` for the portal list and page."""
        self.ensure_one()
        if self.state == "done" and self.picking_type_code in ("outgoing", "dropship"):
            return ("shipped", "Shipped", "text-bg-success")
        if self.state != "done" and self.picking_type_code in ("outgoing", "dropship"):
            picks = self._int_portal_upstream_picks()
            if picks and all(pick.state == "done" for pick in picks):
                return ("picked", "Ready to ship", "text-bg-info")
            if picks:
                return ("open", "Picking", "text-bg-info")
        if self.state == "done":
            return ("picked", "Picked", "text-bg-success")
        if self.backorder_id:
            return ("backordered", "Backordered", "text-bg-warning")
        if self.picking_type_code == "internal":
            return ("open", "Picking", "text-bg-info")
        return ("open", "Preparation", "text-bg-info")

    def _int_portal_delivery_moves(self):
        """Product lines to show on the delivery page. Cancelled lines are left out."""
        self.ensure_one()
        return self.sudo().move_ids.filtered(lambda move: move.state != "cancel")

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
