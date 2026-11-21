from odoo import api, fields, models
from odoo.tools.float_utils import float_compare

OVER_LIMIT_MARKER = "Contact us for a quote on larger quantities."
BACKORDER_SUFFIX = "Backorder"


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    int_backorder = fields.Boolean(
        string="Backorder",
        copy=False,
        readonly=True,
        help="Out of stock with us and Victron when the customer ordered. Not charged at "
             "checkout, kept off invoices until staff release it, and shipped on its own delivery.",
    )
    int_backorder_released = fields.Boolean(
        string="Released for Invoicing",
        copy=False,
        readonly=True,
        help="Set by Release Backorder for Invoicing once the stock has arrived.",
    )

    def _int_is_open_backorder(self):
        """A backorder line that is not invoiceable yet."""
        self.ensure_one()
        return self.int_backorder and not self.int_backorder_released

    def _int_backorder_qty(self):
        """Quantity of this line that is on backorder, in the product's unit.

        Before confirmation this is worked out from stock (or is the whole line once the
        cart has been split at the payment step). After confirmation only split lines count:
        reservations make free stock look empty by then.
        """
        self.ensure_one()
        product = self.product_id
        if not product or self.display_type or self.is_delivery:
            return 0.0
        if self.int_backorder:
            return self.product_uom_id._compute_quantity(self.product_uom_qty, product.uom_id)
        if not self.order_id or self.order_id.state not in ("draft", "sent"):
            return 0.0
        return self.order_id._int_backorder_plan().get(self.id, 0.0)

    def _int_victron_split(self):
        """How this line divides between the warehouse and Victron.

        ``victron`` is the exact supplier quantity still available. Callers that render
        the website must use the capped label, not this number. ``backorder`` is what
        neither side can cover, for products sold when out of stock.
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
            "backorder": 0.0,
            "mixed": False,
            "over": False,
        }
        product = self.product_id
        if (
            not product
            or self.display_type
            or self.is_delivery
            or self.int_backorder
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
        beyond = float_compare(qty, own + victron, precision_rounding=rounding) > 0
        backorderable = template._int_backorderable(product)
        over = beyond and not backorderable
        covered = 0.0 if over else min(later, victron)
        backorder = max(later - covered, 0.0) if backorderable else 0.0
        return {
            "applies": True,
            "own": own,
            "victron": victron,
            "qty": qty,
            "now": now,
            "later": later,
            "covered": covered,
            "backorder": backorder,
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
        if product.product_tmpl_id._int_backorderable(product):
            return False
        cart_qty, own = self.order_id._get_cart_and_free_qty(product)
        victron = product.product_tmpl_id._int_victron_available_qty()
        rounding = product.uom_id.rounding
        if float_compare(cart_qty, max(own, 0.0) + victron, precision_rounding=rounding) > 0:
            return self._int_victron_over_message(cart_qty)
        return False

    def _int_victron_cart_note(self):
        """The line's "ship now · ship later · on backorder" note in the cart."""
        self.ensure_one()
        template = self.product_id.product_tmpl_id
        if self.int_backorder:
            return self.env._(
                "%(qty)s on backorder · no ETA yet",
                qty=template._int_format_qty(self._int_backorder_qty()),
            )
        split = self._int_victron_split()
        if split["over"]:
            return False
        backorder = self._int_backorder_qty() if self.product_id else 0.0
        parts = []
        if split["applies"]:
            if split["now"] > 0:
                parts.append(self.env._(
                    "%(now)s ship now", now=template._int_format_qty(split["now"])
                ) if (split["covered"] > 0 or backorder > 0) else self.env._(
                    "%(now)s ready to ship", now=template._int_format_qty(split["now"])
                ))
            if split["covered"] > 0:
                parts.append(self.env._(
                    "%(later)s ship %(when)s",
                    later=template._int_format_qty(split["covered"]),
                    when=template._int_lead_phrase(),
                ))
        elif backorder > 0:
            qty = self.product_uom_id._compute_quantity(self.product_uom_qty, self.product_id.uom_id)
            now = max(qty - backorder, 0.0)
            if now > 0:
                parts.append(self.env._("%(now)s ship now", now=template._int_format_qty(now)))
        if backorder > 0:
            parts.append(self.env._(
                "%(qty)s on backorder · no ETA yet", qty=template._int_format_qty(backorder)
            ))
        return " · ".join(parts) or False

    def _int_victron_cart_is_over(self):
        self.ensure_one()
        product = self.product_id
        if not product or not product.is_storable or not product.product_tmpl_id._int_victron_feed_qty():
            return False
        if product.product_tmpl_id._int_backorderable(product):
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
        if template._int_victron_feed_qty() > 0 or (product.is_storable and template._int_backorderable(product)):
            if self.shop_warning and marker in self.shop_warning:
                self.shop_warning = False
            return True
        return super()._check_availability()

    def _get_max_line_qty(self):
        template = self.product_id.product_tmpl_id
        if self.product_id.is_storable and not template._int_can_order_online(self.product_id):
            return 0
        if template._int_victron_feed_qty() > 0 or (
            self.product_id.is_storable and template._int_backorderable(self.product_id)
        ):
            return None
        return super()._get_max_line_qty()

    # Invoicing: an open backorder is not billed and does not use credit.

    @api.depends("int_backorder", "int_backorder_released")
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        for line in self.filtered("int_backorder"):
            if not line.int_backorder_released:
                line.qty_to_invoice = 0.0
            elif line.state == "sale":
                # Invoiced before it ships, whatever the product's invoicing policy.
                line.qty_to_invoice = line.product_uom_qty - line.qty_invoiced

    @api.depends("int_backorder", "int_backorder_released")
    def _compute_untaxed_amount_to_invoice(self):
        super()._compute_untaxed_amount_to_invoice()
        for line in self:
            if line.int_backorder and not line.int_backorder_released:
                line.untaxed_amount_to_invoice = 0.0

    @api.depends("int_backorder", "int_backorder_released")
    def _compute_amount_to_invoice(self):
        super()._compute_amount_to_invoice()
        for line in self:
            if line.int_backorder and not line.int_backorder_released:
                line.amount_to_invoice = 0.0
