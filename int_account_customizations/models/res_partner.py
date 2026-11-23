from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    int_terms_warning = fields.Char(
        compute="_compute_int_terms_warning",
        groups="account.group_account_invoice,account.group_account_readonly",
    )

    @api.depends_context("company")
    @api.depends("credit_limit", "use_partner_credit_limit", "property_payment_term_id", "property_supplier_payment_term_id", "parent_id", "is_company")
    def _compute_int_terms_warning(self):
        """Credit limit with no customer payment terms: checkout won't offer Pay on Account."""
        company = self.env.company
        for partner in self:
            warning = False
            if (
                not partner.parent_id
                and company.account_use_credit_limit
                and partner.use_partner_credit_limit
                and (partner.credit_limit or 0.0) > 0
                and not partner._int_is_terms(partner.property_payment_term_id)
            ):
                warning = self.env._(
                    "This customer has a credit limit but no customer payment terms for %(company)s, "
                    "so checkout won't offer Pay on Account. Set Payment Terms under Sales on the "
                    "Sales & Purchase tab.",
                    company=company.name,
                )
                if partner.property_supplier_payment_term_id:
                    warning += " " + self.env._(
                        "The Payment Terms under Purchase are for their vendor bills and don't count."
                    )
            partner.int_terms_warning = warning

    def _int_is_terms(self, term):
        """True for payment terms other than paying straight away."""
        if not term:
            return False
        immediate = self.env.ref("account.account_payment_term_immediate", raise_if_not_found=False)
        if immediate and term == immediate:
            return False
        return any(
            line.nb_days > 0 or line.delay_type != "days_after"
            for line in term.sudo().line_ids
        )

    def _int_on_terms(self, company):
        """True when the company contact has payment terms other than paying straight away."""
        self.ensure_one()
        commercial = self.commercial_partner_id.sudo().with_company(company)
        return self._int_is_terms(commercial.property_payment_term_id)

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
                "Your account doesn't have a credit limit set up yet. Please choose a payment "
                "method below to complete your order. Contact your sales representative to set up terms."
            )
            return result
        if self._int_has_overdue_invoice(company):
            result["reason"] = self.env._(
                "Your account has an overdue invoice. Please choose a payment method below to "
                "complete your order. Once it's paid under Invoices, you can order on terms again."
            )
            return result
        used = max(commercial.credit, 0.0) + max(commercial.credit_to_invoice or 0.0, 0.0)
        available = currency.round(max(limit - used, 0.0))
        result["available"] = available
        if currency.compare_amounts(amount, available) > 0:
            if show_figures:
                result["reason"] = self.env._(
                    "This order is more than your available credit (%(available)s). Please choose a "
                    "payment method below to complete your order. If you'd like to apply for more "
                    "credit, contact your sales representative.",
                    available=currency.format(available),
                )
            else:
                result["reason"] = self.env._(
                    "This order is more than your available credit. Please choose a payment method "
                    "below to complete your order. If you'd like to apply for more credit, contact "
                    "your sales representative."
                )
            return result
        result["eligible"] = True
        return result
