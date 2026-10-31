import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.fields import Command
from odoo.tools.float_utils import float_compare, float_round

from .sale_order_line import OVER_LIMIT_MARKER

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    int_ship_policy_chosen = fields.Boolean(
        string="Customer Chose When to Ship",
        copy=False,
        help="Set when the customer picks one shipment or two at checkout. "
             "Stops the cart from resetting that choice.",
    )

    def _int_victron_needs_ship_choice(self):
        self.ensure_one()
        return any(line._int_victron_split()["mixed"] for line in self.order_line)

    def _int_victron_default_ship_policy(self):
        """Mixed carts ship in two deliveries unless the customer asked to wait."""
        for order in self:
            if order.int_ship_policy_chosen or not order.website_id:
                continue
            if order._int_victron_needs_ship_choice() and order.picking_policy != "direct":
                order.picking_policy = "direct"

    def _int_victron_shortfall_plan(self):
        """(sale line id, quantity to buy) for every line Victron should cover.

        Computed before confirmation, while free stock has not yet been reserved.
        Quantities are shared across the orders in ``self`` so two orders confirmed
        together cannot both claim the same Victron units.
        """
        remaining = {}
        plan = []
        for order in self:
            for line in order.order_line:
                split = line._int_victron_split()
                if not split["applies"]:
                    continue
                template = line.product_id.product_tmpl_id
                if template.id not in remaining:
                    remaining[template.id] = split["victron"]
                rounding = line.product_id.uom_id.rounding
                buy = min(split["later"], remaining[template.id])
                if float_compare(buy, 0.0, precision_rounding=rounding) > 0:
                    plan.append((line.id, buy))
                    remaining[template.id] -= buy
        return plan

    def _verify_updated_quantity(self, order_line, product_id, new_qty, uom_id, **kwargs):
        self.ensure_one()
        product = self.env["product.product"].browse(product_id)
        template = product.product_tmpl_id
        if not product.is_storable:
            return super()._verify_updated_quantity(
                order_line, product_id, new_qty, uom_id, **kwargs
            )
        if not template._int_can_order_online(product):
            return new_qty, self.env._("Currently unavailable — contact us for lead time")
        if template._int_victron_feed_qty() <= 0:
            return super()._verify_updated_quantity(
                order_line, product_id, new_qty, uom_id, **kwargs
            )

        uom = self.env["uom.uom"].browse(uom_id)
        product_uom = product.uom_id
        in_cart, own = self._get_cart_and_free_qty(product)
        in_cart = product_uom._compute_quantity(in_cart, uom)
        own = product_uom._compute_quantity(max(own, 0.0), uom, round=False)
        own = float_round(own, precision_digits=0, rounding_method="DOWN")
        victron = product_uom._compute_quantity(template._int_victron_available_qty(), uom, round=False)
        old_qty = order_line.product_uom_qty if order_line else 0
        total = in_cart + (new_qty - old_qty)
        rounding = uom.rounding or product_uom.rounding
        if float_compare(total, own + victron, precision_rounding=rounding) > 0:
            name = product.with_context(display_default_code=False).display_name
            warning = self.env._(
                "We can't confirm %(qty)s %(product)s online. %(marker)s",
                qty=template._int_format_qty(total),
                product=name,
                marker=self.env._(OVER_LIMIT_MARKER),
            )
            return new_qty, warning
        if order_line:
            order_line.shop_warning = False
        return new_qty, ""

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        result = super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)
        self._int_victron_default_ship_policy()
        return result

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        result = super()._cart_update_line_quantity(line_id, quantity, **kwargs)
        self._int_victron_default_ship_policy()
        return result

    def _int_victron_ship_later_qty(self):
        """Quantity that cannot ship from stock now, per sale line.

        Read before confirmation. Afterwards the reservation makes free stock look empty
        and every unit would look like a Victron remainder.
        """
        later = {}
        for order in self:
            for line in order.order_line:
                split = line._int_victron_split()
                if not split["applies"] or line.product_id.uom_id.is_zero(split["later"]):
                    continue
                later[line.id] = split["later"]
        return later

    def action_confirm(self):
        plan = self._int_victron_shortfall_plan()
        ship_later = self._int_victron_ship_later_qty()
        result = super().action_confirm()
        confirmed = self.filtered(lambda order: order.state in ("sale", "done"))
        if plan and confirmed:
            try:
                self.env["purchase.order"].sudo()._int_victron_add_shortfalls(plan)
            except Exception:
                _logger.exception("Victron RFQ was not created for %s", confirmed.mapped("name"))
                for order in confirmed:
                    order.message_post(
                        body=order.env._(
                            "The Victron purchase order for the out-of-stock units could not be "
                            "created. Set the Victron vendor under Inventory → Settings → "
                            "Victron E-Order, then create the RFQ by hand."
                        ),
                        subtype_xmlid="mail.mt_note",
                    )
        if confirmed:
            confirmed._int_victron_arrange_deliveries(ship_later)
        return result

    def _int_victron_arrange_deliveries(self, later_by_line):
        """Split ship-now orders. A held order stays one delivery.

        ``later_by_line`` maps a sale line id to the quantity that is not in stock,
        in the product's unit.
        """
        for order in self:
            mine = {
                line_id: qty
                for line_id, qty in later_by_line.items()
                if line_id in order.order_line.ids
            }
            if not mine:
                continue
            if order.picking_policy == "one":
                # Two-step warehouses only have the pick at confirmation. The
                # customer delivery is created when that pick is finished.
                open_pickings = order.picking_ids.filtered(
                    lambda picking: picking.state not in ("done", "cancel")
                )
                order._int_victron_note_wait(open_pickings)
                continue
            sources = {}
            for line in order.order_line:
                later_qty = mine.get(line.id) or 0.0
                if not line.product_id or line.product_id.uom_id.is_zero(later_qty):
                    continue
                moves = line.move_ids.filtered(lambda move: move.state not in ("done", "cancel"))
                roots = moves.filtered(lambda move: not (move.move_dest_ids & moves))
                for root in roots:
                    order._int_victron_peel_later(root, later_qty, sources)
            later_moves = self.env["stock.move"]
            for move in sources:
                later_moves |= move
            clones = order._int_victron_place_later_moves(later_moves, sources)
            order._int_victron_note_ship_now(clones, later_moves)

    def _int_victron_peel_later(self, move, later_qty, sources, seen=None):
        """Move ``later_qty`` off ``move`` and the pick that feeds it.

        The original move keeps what can ship now. The returned move is the
        Victron portion, still without its own picking.
        """
        seen = seen if seen is not None else {}
        if move.id in seen:
            return seen[move.id]
        product = move.product_id
        rounding = product.uom_id.rounding
        full = move.product_uom._compute_quantity(move.product_uom_qty, product.uom_id)
        if float_compare(later_qty, full, precision_rounding=rounding) >= 0:
            later = move
        else:
            vals = move._split(later_qty)
            if not vals:
                seen[move.id] = self.env["stock.move"]
                return seen[move.id]
            vals = vals[0]
            vals["picking_id"] = False
            later = self.env["stock.move"].create(vals)
        sources[later] = move.picking_id
        seen[move.id] = later
        new_origs = self.env["stock.move"]
        old_origs = move.move_orig_ids
        for orig in list(old_origs):
            new_origs |= self._int_victron_peel_later(orig, later_qty, sources, seen)
        if later != move:
            later.write({"move_orig_ids": [Command.set(new_origs.ids)]})
            # A newly split pick must feed only the follow-up delivery. An unsplit
            # pick already feeds the original delivery and has to keep that link.
            for orig in new_origs - old_origs:
                orig.write({"move_dest_ids": [Command.set(later.ids)]})
        return later

    def _int_victron_place_later_moves(self, later_moves, sources):
        clones = {}
        for later in later_moves:
            source = sources.get(later)
            if not source or source.state in ("done", "cancel"):
                continue
            staying = source.move_ids.filtered(
                lambda move: move.state != "cancel"
            ) - later_moves
            if not staying:
                if not later.picking_id:
                    later.picking_id = source
                continue
            clone = clones.get(source.id)
            if not clone:
                vals = {
                    "name": "/",
                    "move_ids": [],
                    "move_line_ids": [],
                    "backorder_id": source.id,
                }
                if "carrier_tracking_ref" in source._fields:
                    vals["carrier_tracking_ref"] = False
                if "carrier_price" in source._fields:
                    vals["carrier_price"] = 0.0
                clone = source.copy(vals)
                clones[source.id] = clone
            later.write({"picking_id": clone.id})
            later.move_line_ids.write({"picking_id": clone.id})
        drafts = later_moves.filtered(lambda move: move.state == "draft")
        if drafts:
            drafts.with_context(bypass_entire_pack=True)._action_confirm(
                merge=False, create_proc=False,
            )
        return clones

    def _int_victron_purchase_orders(self):
        self.ensure_one()
        lines = self.env["purchase.order.line"].sudo().search([
            ("int_source_sale_line_id", "in", self.order_line.ids),
            ("order_id.state", "!=", "cancel"),
        ])
        return lines.order_id

    def _int_victron_po_links(self):
        orders = self._int_victron_purchase_orders()
        if not orders:
            return self.env._("no purchase order has been raised yet")
        return Markup(", ").join(order._get_html_link() for order in orders)

    def _int_victron_record_note(self, picking, body):
        """Put the note on the transfer itself and in its chatter.

        The warehouse reads the pick, which is the only transfer that exists
        at confirmation when delivery is two steps.
        """
        picking.message_post(body=body, subtype_xmlid="mail.mt_note")
        paragraph = Markup("<p>%s</p>") % body
        picking.note = (picking.note or Markup("")) + paragraph

    def _int_victron_note_wait(self, pickings):
        link = self._int_victron_po_links()
        body = self.env._(
            "Customer has elected to wait for extra stock to arrive. "
            "Fulfil this order with stock from PO %(po)s.",
            po=link,
        )
        for picking in pickings:
            self._int_victron_record_note(picking, body)

    def _int_victron_note_ship_now(self, clones, later_moves):
        link = self._int_victron_po_links()
        later_body = self.env._(
            "Stock to be sent from the Victron order. Purchase %(po)s has been "
            "raised to fill this order.",
            po=link,
        )
        noted = self.env["stock.picking"]
        for source_id, clone in clones.items():
            source = self.env["stock.picking"].browse(source_id)
            if source.state == "cancel":
                continue
            noted |= source
            self._int_victron_record_note(source, self.env._(
                "Shipment of immediate stock. The rest will be fulfilled on %(delivery)s.",
                delivery=clone._get_html_link(),
            ))
            self._int_victron_record_note(clone, later_body)
        if noted:
            return
        for picking in later_moves.picking_id.filtered(lambda item: item.state != "cancel"):
            self._int_victron_record_note(picking, later_body)

    def _action_cancel(self):
        result = super()._action_cancel()
        self.env["purchase.order"].sudo()._int_victron_on_sale_cancel(self)
        return result

    @api.model
    def _int_victron_parties(self):
        """Vendor and buyer for Victron RFQs.

        The buyer stored in settings wins. Otherwise the user named Casey Shirts is used,
        which is who reviews these orders.
        """
        icp = self.env["ir.config_parameter"].sudo()
        buyer_id = int(icp.get_param("int_victron.buyer_user_id") or 0)
        buyer = self.env["res.users"].browse(buyer_id).exists()
        buyer_from_settings = bool(buyer)
        if not buyer:
            buyer = self.env["res.users"].search([("name", "=ilike", "Casey Shirts")], limit=1)
        vendor_id = int(icp.get_param("int_victron.vendor_partner_id") or 0)
        vendor = self.env["res.partner"].browse(vendor_id).exists()
        if not vendor:
            vendor = self.env["res.partner"].search(
                [("name", "ilike", "Victron"), ("supplier_rank", ">", 0)],
                limit=1,
            ) or self.env["res.partner"].search([("name", "ilike", "Victron")], limit=1)
        if buyer and vendor and (buyer_from_settings or not vendor.buyer_id):
            vendor.buyer_id = buyer
        return vendor, buyer
