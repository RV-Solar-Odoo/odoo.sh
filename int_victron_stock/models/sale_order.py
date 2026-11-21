import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare, float_round

from .sale_order_line import BACKORDER_SUFFIX, OVER_LIMIT_MARKER

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    int_has_open_backorder = fields.Boolean(
        string="Has Backorder",
        compute="_compute_int_has_open_backorder",
        help="Backordered lines are waiting to be released for invoicing.",
    )
    int_ship_policy_chosen = fields.Boolean(
        string="Customer Chose When to Ship",
        copy=False,
        help="Set when the customer picks one shipment or two at checkout. "
             "Stops the cart from resetting that choice.",
    )

    @api.depends("order_line.int_backorder", "order_line.int_backorder_released", "order_line.product_uom_qty")
    def _compute_int_has_open_backorder(self):
        for order in self:
            order.int_has_open_backorder = bool(order.order_line.filtered(
                lambda line: line._int_is_open_backorder() and line.product_uom_qty
            ))

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
        if template._int_backorderable(product):
            # Anything we and Victron can't cover goes on backorder. No cap, no warning.
            if order_line:
                order_line.shop_warning = False
            return new_qty, ""
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
        self._int_backorder_merge()
        result = super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)
        self._int_victron_default_ship_policy()
        return result

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        line_id, quantity = self._int_backorder_merge(line_id, quantity)
        result = super()._cart_update_line_quantity(line_id, quantity, **kwargs)
        self._int_victron_default_ship_policy()
        return result

    # Backorders

    def _int_backorder_plan(self):
        """{sale line id: quantity on backorder} for a cart, in each product's unit.

        Our free stock fills lines first, then Victron's, then the rest is backordered.
        Both are shared across lines of the same product. Lines already split off as
        backorders, combo items and reward lines are left out.
        """
        self.ensure_one()
        plan = {}
        own_left = {}
        victron_left = {}
        for line in self.order_line.sorted("id"):
            product = line.product_id
            if (
                not product
                or line.display_type
                or line.is_delivery
                or line.int_backorder
                or line.combo_item_id
                or not product.is_storable
                or ("reward_id" in line._fields and line.reward_id)
            ):
                continue
            template = product.product_tmpl_id
            if not template._int_backorderable(product):
                continue
            qty = line.product_uom_id._compute_quantity(line.product_uom_qty, product.uom_id)
            if product.id not in own_left:
                own_left[product.id] = max(self._get_free_qty(product), 0.0)
            if template.id not in victron_left:
                victron_left[template.id] = template._int_victron_available_qty()
            from_own = min(qty, own_left[product.id])
            own_left[product.id] -= from_own
            from_victron = min(qty - from_own, victron_left[template.id])
            victron_left[template.id] -= from_victron
            backorder = qty - from_own - from_victron
            if float_compare(backorder, 0.0, precision_rounding=product.uom_id.rounding) > 0:
                plan[line.id] = backorder
        return plan

    def _int_has_backorder(self):
        self.ensure_one()
        if self.order_line.filtered(lambda line: line._int_is_open_backorder() and line.product_uom_qty):
            return True
        return self.state in ("draft", "sent") and bool(self._int_backorder_plan())

    def _int_backorder_lines(self):
        """Backorder lines still waiting to be released for invoicing."""
        self.ensure_one()
        return self.order_line.filtered(lambda line: line._int_is_open_backorder() and line.product_uom_qty)

    def _int_backorder_amount(self):
        """Tax-included value of the open backorder lines. Not charged at checkout."""
        self.ensure_one()
        return self.currency_id.round(sum(self._int_backorder_lines().mapped("price_total")))

    def _int_pay_now_amount(self):
        """What checkout charges: the order total less the open backorder lines."""
        self.ensure_one()
        return self.currency_id.round(max(self.amount_total - self._int_backorder_amount(), 0.0))

    @staticmethod
    def _int_backorder_name(name):
        return f"{name}\n{BACKORDER_SUFFIX}" if not (name or "").endswith(BACKORDER_SUFFIX) else name

    @staticmethod
    def _int_plain_name(name):
        suffix = f"\n{BACKORDER_SUFFIX}"
        return name[: -len(suffix)] if (name or "").endswith(suffix) else name

    def _int_backorder_split(self):
        """Move each backordered quantity onto its own Backorder line, at the payment step.

        The split fixes what is charged now. Both lines keep the price the customer saw,
        so a smaller quantity does not move a line to another price break.
        """
        for order in self:
            if order.state not in ("draft", "sent"):
                continue
            plan = order._int_backorder_plan()
            for line in order.order_line.filtered(lambda item: item.id in plan):
                product = line.product_id
                backorder = product.uom_id._compute_quantity(plan[line.id], line.product_uom_id)
                rounding = line.product_uom_id.rounding
                price = line.price_unit
                if float_compare(backorder, line.product_uom_qty, precision_rounding=rounding) >= 0:
                    line.write({"int_backorder": True, "name": order._int_backorder_name(line.name)})
                    continue
                technical = line.technical_price_unit
                new_line = line.copy({
                    "order_id": order.id,
                    "product_uom_qty": backorder,
                    "price_unit": price,
                    "technical_price_unit": technical,
                    "int_backorder": True,
                    "name": order._int_backorder_name(line.name),
                    "sequence": line.sequence,
                })
                line.product_uom_qty = line.product_uom_qty - backorder
                for item in (line, new_line):
                    if order.currency_id.compare_amounts(item.price_unit, price):
                        item.price_unit = price
            if order.order_line.filtered("int_backorder") and hasattr(order, "_update_programs_and_rewards"):
                order._update_programs_and_rewards()

    def _int_backorder_merge(self, line_id=None, quantity=None):
        """Put split Backorder lines back on their line, so the cart is editable again.

        ``line_id`` and ``quantity`` are a cart update about to happen. When that line was
        a Backorder line that has just been merged, the update moves to the line it joined.
        """
        for order in self:
            if order.state not in ("draft", "sent"):
                continue
            for backorder in order.order_line.filtered("int_backorder"):
                sibling = order.order_line.filtered(
                    lambda line: line != backorder
                    and not line.int_backorder
                    and line.product_id == backorder.product_id
                    and line.product_uom_id == backorder.product_uom_id
                    and not line.combo_item_id
                    and line.product_no_variant_attribute_value_ids == backorder.product_no_variant_attribute_value_ids
                    and not ("reward_id" in line._fields and line.reward_id)
                )[:1]
                if not sibling:
                    backorder.write({"int_backorder": False, "name": order._int_plain_name(backorder.name)})
                    continue
                if line_id == backorder.id and quantity is not None:
                    line_id, quantity = sibling.id, sibling.product_uom_qty + quantity
                sibling.product_uom_qty += backorder.product_uom_qty
                backorder.unlink()
        return line_id, quantity

    def _allow_express_checkout(self):
        """Express checkout charges the whole cart, so it is off when something is backordered."""
        allowed = super()._allow_express_checkout()
        return allowed and not any(order._int_has_backorder() for order in self)

    def _get_prepayment_required_amount(self):
        amount = super()._get_prepayment_required_amount()
        if self.state in ("draft", "sent") and self._int_backorder_lines():
            return min(amount, self._int_pay_now_amount())
        return amount

    def _is_paid(self):
        """Paid once everything except the open backorder lines is covered."""
        if self._int_backorder_lines():
            return self.currency_id.compare_amounts(self.amount_paid, self._int_pay_now_amount()) >= 0
        return super()._is_paid()

    def _force_lines_to_invoice_policy_order(self):
        super()._force_lines_to_invoice_policy_order()
        for line in self.order_line.filtered(lambda item: item._int_is_open_backorder()):
            line.qty_to_invoice = 0.0

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
            confirmed._int_backorder_arrange()
        return result

    def _int_backorder_arrange(self):
        """Give the Backorder lines their own delivery and put them on a draft backorder PO."""
        for order in self:
            lines = order.order_line.filtered(lambda line: line.int_backorder and line.product_uom_qty)
            if not lines:
                continue
            sources = {}
            for line in lines:
                moves = line.move_ids.filtered(lambda move: move.state not in ("done", "cancel"))
                roots = moves.filtered(lambda move: not (move.move_dest_ids & moves))
                for root in roots:
                    full = root.product_uom._compute_quantity(root.product_uom_qty, root.product_id.uom_id)
                    order._int_victron_peel_later(root, full, sources)
            later_moves = self.env["stock.move"]
            for move in sources:
                later_moves |= move
            clones = order._int_victron_place_later_moves(later_moves, sources)
            try:
                self.env["purchase.order"].sudo()._int_add_backorders(lines)
            except Exception:
                _logger.exception("Backorder purchase order was not created for %s", order.name)
                order.message_post(
                    body=order.env._(
                        "The backorder purchase order could not be created. Create it by hand."
                    ),
                    subtype_xmlid="mail.mt_note",
                )
            order._int_backorder_note(clones, later_moves)

    def _int_backorder_purchase_orders(self):
        self.ensure_one()
        lines = self.env["purchase.order.line"].sudo().search([
            ("int_source_sale_line_id", "in", self.order_line.filtered("int_backorder").ids),
            ("order_id.int_backorder_po", "=", True),
            ("order_id.state", "!=", "cancel"),
        ])
        return lines.order_id

    def _int_backorder_note(self, clones, later_moves):
        orders = self._int_backorder_purchase_orders()
        po = Markup(", ").join(order._get_html_link() for order in orders) if orders else self.env._(
            "no purchase order yet"
        )
        body = self.env._(
            "Backorder: out of stock with us and our suppliers when ordered. Not invoiced yet. "
            "Ship once the stock arrives on %(po)s and the order has been released for invoicing.",
            po=po,
        )
        noted = self.env["stock.picking"]
        for source_id, clone in clones.items():
            source = self.env["stock.picking"].browse(source_id)
            if source.state == "cancel":
                continue
            noted |= clone
            self._int_victron_record_note(source, self.env._(
                "The backordered items will ship on %(delivery)s.", delivery=clone._get_html_link(),
            ))
            self._int_victron_record_note(clone, body)
        for picking in later_moves.picking_id.filtered(lambda item: item.state != "cancel") - noted:
            self._int_victron_record_note(picking, body)
        self.message_post(body=self.env._(
            "Backordered items are not charged and stay off invoices until you click "
            "Release Backorder for Invoicing. Purchase: %(po)s.",
            po=po,
        ), subtype_xmlid="mail.mt_note")

    def action_int_release_backorder(self):
        """Staff: the backorder stock is here, so its lines can now be invoiced."""
        for order in self:
            lines = order._int_backorder_lines()
            if not lines:
                raise UserError(order.env._("%(order)s has no backorder waiting to be released.", order=order.name))
            lines.write({"int_backorder_released": True})
            order.message_post(body=order.env._(
                "%(user)s released the backorder for invoicing: %(items)s. Add backorder "
                "shipping if it applies, then invoice as usual.",
                user=order.env.user.name,
                items=", ".join(
                    f"{line.product_id.display_name} × {order.env['product.template']._int_format_qty(line.product_uom_qty)}"
                    for line in lines
                ),
            ), subtype_xmlid="mail.mt_note")
        return True

    def _int_backorder_cancel(self, lines, user):
        """Cancel backordered lines that have not shipped. Returns the cancelled lines."""
        self.ensure_one()
        lines = lines.filtered(
            lambda line: line.order_id == self and line.int_backorder and line.product_uom_qty
        )
        if not lines:
            return lines
        moves = self.env["stock.move"].sudo().search([
            ("sale_line_id", "in", lines.ids),
            ("state", "not in", ("done", "cancel")),
        ])
        if self.env["stock.move"].sudo().search_count([
            ("sale_line_id", "in", lines.ids), ("state", "=", "done"),
            ("location_dest_id.usage", "=", "customer"),
        ]):
            raise UserError(self.env._("The backordered items have already shipped."))
        moves._action_cancel()
        self.env["purchase.order"].sudo()._int_backorder_drop_lines(lines)
        names = ", ".join(
            f"{line.product_id.display_name} × {self.env['product.template']._int_format_qty(line.product_uom_qty)}"
            for line in lines
        )
        order = self.sudo()
        locked = order.locked
        if locked:
            order.locked = False
        lines.sudo().write({"product_uom_qty": 0.0})
        if locked:
            order.locked = True
        order.message_post(body=self.env._(
            "%(user)s cancelled the backordered items: %(items)s.", user=user.name, items=names,
        ), subtype_xmlid="mail.mt_note")
        return lines

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
            ("order_id.int_victron_rfq", "=", True),
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
