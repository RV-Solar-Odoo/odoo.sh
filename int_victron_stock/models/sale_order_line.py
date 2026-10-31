from odoo import models
from odoo.tools.float_utils import float_compare

OVER_LIMIT_MARKER = "Contact us for a quote on larger quantities."


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _int_victron_split(self):
        """How this line divides between the warehouse and Victron.

        ``victron`` is the exact supplier quantity still available. Callers that render
        the website must use the capped label, not this number.
        """
        self.ensure_one()
        empty = {
            "applies": False,
            "own": 0.0,
            "victron": 0.0,
            "qty": 0.0,
            "now": 0.0,
            "later": 0.0,
            "covered": 0.0,
            "mixed": False,
            "over": False,
        }
        product = self.product_id
        if (
            not product
            or self.display_type
            or self.is_delivery
            or not product.is_storable
        ):
            return empty
        template = product.product_tmpl_id
        feed = template._int_victron_feed_qty()
        if feed <= 0:
            return empty
        if self.order_id:
            own = self.order_id._get_free_qty(product)
        else:
            own = product.free_qty
        own = max(own, 0.0)
        victron = template._int_victron_available_qty()
        qty = self.product_uom_id._compute_quantity(self.product_uom_qty, product.uom_id)
        now = min(qty, own)
        later = max(qty - now, 0.0)
        rounding = product.uom_id.rounding
        over = float_compare(qty, own + victron, precision_rounding=rounding) > 0
        covered = 0.0 if over else min(later, victron)
        return {
            "applies": True,
            "own": own,
            "victron": victron,
            "qty": qty,
            "now": now,
            "later": later,
            "covered": covered,
            "mixed": (
                float_compare(now, 0.0, precision_rounding=rounding) > 0
                and float_compare(covered, 0.0, precision_rounding=rounding) > 0
                and not over
            ),
            "over": over,
        }

    def _int_victron_over_message(self, qty=None):
        self.ensure_one()
        shown = self.product_id.product_tmpl_id._int_format_qty(
            self.product_uom_qty if qty is None else qty
        )
        name = self.product_id.with_context(display_default_code=False).display_name
        return self.env._(
            "We can't confirm %(qty)s %(product)s online. %(marker)s",
            qty=shown,
            product=name,
            marker=self.env._(OVER_LIMIT_MARKER),
        )

    def _int_victron_checkout_warning(self):
        """Persistent cart message. Recomputed, so it does not reveal a stock figure."""
        self.ensure_one()
        product = self.product_id
        if not product or not product.product_tmpl_id._int_victron_feed_qty():
            return False
        cart_qty, own = self.order_id._get_cart_and_free_qty(product)
        victron = product.product_tmpl_id._int_victron_available_qty()
        rounding = product.uom_id.rounding
        if float_compare(cart_qty, max(own, 0.0) + victron, precision_rounding=rounding) > 0:
            return self._int_victron_over_message(cart_qty)
        return False

    def _int_victron_cart_note(self):
        self.ensure_one()
        split = self._int_victron_split()
        if not split["applies"] or split["over"]:
            return False
        template = self.product_id.product_tmpl_id
        phrase = template._int_lead_phrase()
        now = template._int_format_qty(split["now"])
        later = template._int_format_qty(split["covered"])
        if split["now"] > 0 and split["covered"] > 0:
            return self.env._(
                "%(now)s ship now · %(later)s ship %(when)s",
                now=now,
                later=later,
                when=phrase,
            )
        if split["covered"] > 0:
            return self.env._("%(later)s ship %(when)s", later=later, when=phrase)
        if split["now"] > 0:
            return self.env._("%(now)s ready to ship", now=now)
        return False

    def _int_victron_cart_is_over(self):
        self.ensure_one()
        product = self.product_id
        if not product or not product.is_storable or not product.product_tmpl_id._int_victron_feed_qty():
            return False
        cart_qty, own = self.order_id._get_cart_and_free_qty(product)
        victron = product.product_tmpl_id._int_victron_available_qty()
        return float_compare(
            cart_qty,
            max(own, 0.0) + victron,
            precision_rounding=product.uom_id.rounding,
        ) > 0

    def _check_availability(self):
        product = self.product_id
        template = product.product_tmpl_id
        if product.is_storable and not template._int_can_order_online(product):
            self.shop_warning = self.env._("Currently unavailable — contact us for lead time")
            return False
        if self._int_victron_cart_is_over():
            self.shop_warning = self._int_victron_over_message(
                self.order_id._get_cart_qty(self.product_id.id)
            )
            return False
        marker = self.env._(OVER_LIMIT_MARKER)
        if template._int_victron_feed_qty() > 0:
            if self.shop_warning and marker in self.shop_warning:
                self.shop_warning = False
            return True
        return super()._check_availability()

    def _get_max_line_qty(self):
        template = self.product_id.product_tmpl_id
        if self.product_id.is_storable and not template._int_can_order_online(self.product_id):
            return 0
        if template._int_victron_feed_qty() > 0:
            return None
        return super()._get_max_line_qty()
