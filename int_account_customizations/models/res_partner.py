from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _int_on_terms(self, company):
        """True when the company contact has payment terms other than paying straight away."""
        self.ensure_one()
        commercial = self.commercial_partner_id.sudo().with_company(company)
        term = commercial.property_payment_term_id
        if not term:
            return False
        immediate = self.env.ref("account.account_payment_term_immediate", raise_if_not_found=False)
        if immediate and term == immediate:
            return False
        return any(
            line.nb_days > 0 or line.delay_type != "days_after"
            for line in term.line_ids
        )

    def _int_has_overdue_invoice(self, company):
        self.ensure_one()
        commercial = self.commercial_partner_id
        return bool(self.env["account.move"].sudo().search_count([
            ("company_id", "=", company.id),
            ("commercial_partner_id", "=", commercial.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")),
            ("invoice_date_due", "<", fields.Date.context_today(self)),
        ], limit=1))

    def _int_terms_status(self, company, amount, show_figures=False):
        """Whether this customer can place an order for ``amount`` on account.

        Returns a dict:
        - ``on_terms``: the company contact has payment terms (Net 10th, Net 30, ...).
        - ``eligible``: they can order this amount on account now.
        - ``reason``: why not, for the checkout page. False when not on terms at all.
        - ``term``: the payment terms.
        - ``available``: credit left, in the company currency.

        Credit used is the same figure as the credit card on My Portal: open
        receivables plus confirmed orders not yet invoiced. Open backorders are not in
        it, because they are not invoiceable until released. ``show_figures`` puts the
        available amount in the reason, for people allowed to see credit.
        """
        self.ensure_one()
        commercial = self.commercial_partner_id.sudo().with_company(company)
        result = {
            "on_terms": False,
            "eligible": False,
            "reason": False,
            "term": commercial.property_payment_term_id,
            "available": 0.0,
        }
        if not self._int_on_terms(company):
            return result
        result["on_terms"] = True
        currency = company.currency_id
        limit = commercial.credit_limit or 0.0
        if not company.sudo().account_use_credit_limit or limit <= 0:
            result["reason"] = self.env._(
                "Your account doesn't have a credit limit yet, so this order is paid by card. "
                "Contact us to set one up."
            )
            return result
        if self._int_has_overdue_invoice(company):
            result["reason"] = self.env._(
                "You have an overdue invoice, so this order is paid by card. Pay it under "
                "Invoices to order on terms again."
            )
            return result
        used = max(commercial.credit, 0.0) + max(commercial.credit_to_invoice or 0.0, 0.0)
        available = currency.round(max(limit - used, 0.0))
        result["available"] = available
        if currency.compare_amounts(amount, available) > 0:
            if show_figures:
                result["reason"] = self.env._(
                    "This order is more than your available credit (%(available)s), so it is paid "
                    "by card. Contact us if you need more credit.",
                    available=currency.format(available),
                )
            else:
                result["reason"] = self.env._(
                    "This order is more than your available credit, so it is paid by card. "
                    "Ask your account owner, or contact us."
                )
            return result
        result["eligible"] = True
        return result
