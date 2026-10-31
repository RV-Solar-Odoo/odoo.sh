import logging

from odoo import api, fields, models
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
        if not product.is_storable or template._int_victron_feed_qty() <= 0:
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

    def action_confirm(self):
        plan = self._int_victron_shortfall_plan()
        split_orders = self.filtered(
            lambda order: order._int_victron_needs_ship_choice() and order.picking_policy == "direct"
        )
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
        for order in split_orders.filtered(lambda item: item.state in ("sale", "done")):
            order.message_post(
                body=order.env._(
                    "This order ships in more than one delivery. The customer was charged "
                    "shipping once, for the full order. Do not add a second shipping charge "
                    "for the follow-up shipment."
                ),
                subtype_xmlid="mail.mt_note",
            )
        return result

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
