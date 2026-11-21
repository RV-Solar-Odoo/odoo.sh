from odoo import _, fields, models
from odoo.exceptions import UserError

from .sale_order import CANCEL_REASONS


class SaleOrder(models.Model):
    _inherit = "sale.order"

    int_on_account = fields.Boolean(
        string="Placed on Account",
        copy=False,
        readonly=True,
        help="Placed at checkout on the dealer's payment terms, without a card payment.",
    )
    int_cancel_scope = fields.Selection(
        [
            ("order", "Whole order"),
            ("backorder", "Backordered items"),
        ],
        string="Cancellation covers",
        default="order",
        copy=False,
    )

    def _get_no_effect_on_threshold_lines(self):
        """Coupons and promotions only count, and only discount, what is paid for now.

        Open backorder lines are left out of coupon minimums and discounts. A dealer's
        own discount is in the pricelist price, so it still applies to them.
        """
        lines = super()._get_no_effect_on_threshold_lines()
        return lines | self.order_line.filtered(lambda line: line._int_is_open_backorder())

    # What checkout charges

    def _int_amount_due_now(self):
        """What the customer pays at checkout: nothing on account, otherwise the order
        less its backordered lines."""
        self.ensure_one()
        if self.int_on_account:
            return 0.0
        return self._int_pay_now_amount()

    def _int_terms_for(self, user):
        """Whether ``user`` can place this cart on their company's payment terms.

        Same dict as ``res.partner._int_terms_status``. Only a logged-in portal user
        ordering for their own company can use it.
        """
        self.ensure_one()
        empty = {"on_terms": False, "eligible": False, "reason": False, "term": False, "available": 0.0}
        if user._is_public() or not user.share:
            return empty
        commercial = user.partner_id.commercial_partner_id
        if self.partner_id.commercial_partner_id != commercial:
            return empty
        if user.int_portal_ordering_blocked():
            return empty
        return commercial._int_terms_status(
            self.company_id,
            self._int_pay_now_amount(),
            show_figures=user.int_portal_can("view_credit"),
        )

    def _int_place_without_payment(self, mode, user):
        """Confirm the cart with no card payment.

        ``account``: on the dealer's payment terms, when they are eligible for this amount.
        ``backorder``: everything in the cart is backordered, so there is nothing to pay yet.
        """
        self.ensure_one()
        if self.state not in ("draft", "sent"):
            raise UserError(_("This order has already been placed."))
        if user.int_portal_ordering_blocked():
            raise UserError(_("Ask your account owner to order."))
        self._check_cart_is_ready_to_be_paid()
        if mode == "account":
            status = self._int_terms_for(user)
            if not status["eligible"]:
                raise UserError(status["reason"] or _("This order can't be placed on account. Pay by card."))
            values = {"int_on_account": True}
            if status["term"]:
                values["payment_term_id"] = status["term"].id
            self.write(values)
            body = _(
                "Placed on account at checkout by %(user)s (%(term)s). Nothing was charged. "
                "Invoice it as usual.",
                user=user.name,
                term=status["term"].display_name if status["term"] else _("payment terms"),
            )
        elif mode == "backorder":
            if not self._int_backorder_lines() or self.currency_id.compare_amounts(self._int_pay_now_amount(), 0.0) > 0:
                raise UserError(_("This order needs a payment."))
            body = _("Placed at checkout by %(user)s with everything on backorder. Nothing was charged.", user=user.name)
        else:
            raise UserError(_("Choose how to place the order."))
        self._validate_order()
        self.message_post(body=body, subtype_xmlid="mail.mt_note")
        return True

    # Cancelling backordered items

    def _int_cancellable_backorder_lines(self):
        """Backordered lines that have not shipped."""
        self.ensure_one()
        lines = self.order_line.filtered(lambda line: line.int_backorder and line.product_uom_qty)
        if not lines:
            return lines
        shipped = self.env["stock.move"].sudo().search([
            ("sale_line_id", "in", lines.ids),
            ("state", "=", "done"),
            ("location_dest_id.usage", "=", "customer"),
        ]).sale_line_id
        return lines - shipped

    def _int_can_cancel_backorder(self, user):
        self.ensure_one()
        return (
            self.state == "sale"
            and user.int_portal_can("cancel_orders")
            and self._int_owned_by(user)
            and self.int_cancel_state != "requested"
            and bool(self._int_cancellable_backorder_lines())
        )

    def int_portal_cancel_backorder(self, user, reason, note):
        """Customer cancels the backordered items. Returns "cancelled" or "requested".

        Cancelled straight away while the backorder is only on a draft purchase order.
        Once the purchase is confirmed with the vendor, or the items have been released
        for invoicing, it becomes a request for staff.
        """
        self.ensure_one()
        if not user.int_portal_can("cancel_orders") or not self._int_owned_by(user):
            raise UserError(_("You cannot cancel items on this order."))
        if self.state != "sale":
            raise UserError(_("Only a confirmed order can be changed."))
        if self.int_cancel_state == "requested":
            raise UserError(_("A cancellation request is already open."))
        if reason not in dict(CANCEL_REASONS):
            raise UserError(_("Choose a reason."))
        lines = self._int_cancellable_backorder_lines()
        if not lines:
            raise UserError(_("There are no backordered items left to cancel."))
        order = self.sudo()
        confirmed = self.env["purchase.order"].sudo()._int_backorder_confirmed_lines(lines)
        if not confirmed and not lines.filtered("int_backorder_released"):
            order._int_backorder_cancel(lines, user)
            order.message_post(body=_(
                "Reason: %(reason)s. %(note)s",
                reason=dict(CANCEL_REASONS).get(reason, ""),
                note=note or "",
            ), subtype_xmlid="mail.mt_note")
            return "cancelled"
        order.write({
            "int_cancel_state": "requested",
            "int_cancel_scope": "backorder",
            "int_cancel_reason": reason,
            "int_cancel_note": note or False,
            "int_cancel_refund_pref": False,
            "int_cancel_requested_by": user.id,
            "int_cancel_requested_on": fields.Datetime.now(),
            "int_cancel_decided_by": False,
            "int_cancel_decision_note": False,
        })
        order.message_post(body=_(
            "Cancellation of the backordered items requested. The purchase is already confirmed "
            "with the vendor, or the items were released for invoicing. Nothing has been cancelled yet."
        ))
        order._int_alert_cancel_request()
        return "requested"

    def int_portal_request_cancel(self, user, reason, note, preference):
        self.ensure_one()
        result = super().int_portal_request_cancel(user, reason, note, preference)
        self.sudo().int_cancel_scope = "order"
        return result

    def int_confirm_cancellation(self, staff, preference, note):
        """Staff approval. A backorder request cancels only the backordered items."""
        self.ensure_one()
        if self.int_cancel_scope != "backorder":
            return super().int_confirm_cancellation(staff, preference, note)
        if not staff.has_group("sales_team.group_sale_manager"):
            raise UserError(_("Only a sales manager can confirm a cancellation."))
        if self.int_cancel_state != "requested":
            raise UserError(_("There is no open cancellation request."))
        lines = self._int_cancellable_backorder_lines()
        if not lines:
            raise UserError(_("The backordered items have shipped since the request. Nothing was cancelled."))
        invoiced = lines.filtered(lambda line: line.qty_invoiced)
        self._int_backorder_cancel(lines, staff)
        self.write({
            "int_cancel_state": "approved",
            "int_cancel_decided_by": staff.id,
            "int_cancel_decision_note": note or False,
        })
        body = _("Cancellation of the backordered items confirmed.")
        if invoiced:
            body = _(
                "%(body)s They were already invoiced: issue a credit note for %(items)s.",
                body=body,
                items=", ".join(invoiced.product_id.mapped("display_name")),
            )
        self.message_post(body=body)
        return True


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _int_shipping_quote_qty(self):
        """Backordered units ship later and are charged shipping then."""
        qty = super()._int_shipping_quote_qty()
        backorder = self._int_backorder_qty()
        if not backorder:
            return qty
        backorder = self.product_id.uom_id._compute_quantity(backorder, self.product_uom_id)
        return max(qty - backorder, 0.0)
