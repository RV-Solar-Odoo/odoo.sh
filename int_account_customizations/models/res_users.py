from odoo import models

CREDIT_ROLES = {"owner", "accountant"}


class ResUsers(models.Model):
    _inherit = "res.users"

    def _int_portal_company(self):
        """Company of the website the visitor is on, otherwise the current company."""
        self.ensure_one()
        website_id = self.env.context.get("website_id")
        if website_id and "website" in self.env:
            website = self.env["website"].sudo().browse(website_id).exists()
            if website.company_id:
                return website.company_id
        return self.env.company

    def _int_portal_can_view_credit(self, company=None):
        """Who may see the credit card. The one place to extend for portal roles.

        Internal users always can, so staff can check the card. Portal users must
        belong to an approved dealer company, with the Owner or Accountant role.
        """
        self.ensure_one()
        if self._is_public():
            return False
        if self.has_group("base.group_user"):
            return True
        if not self._int_portal_is_dealer(company or self._int_portal_company()):
            return False
        role = self.partner_id.sudo().int_portal_role or "owner"
        return role in CREDIT_ROLES

    def _int_portal_is_dealer(self, company):
        """Same rule as the shop's dealer pricing: the company contact's pricelist
        is set and is not the public user's. Pending applicants and retail
        customers stay on the public pricelist."""
        self.ensure_one()
        commercial = self.partner_id.sudo().commercial_partner_id
        public = self.env.ref("base.public_user").sudo().partner_id.commercial_partner_id
        if not commercial or commercial == public:
            return False
        pricelist = commercial.with_company(company).property_product_pricelist
        public_pricelist = public.with_company(company).property_product_pricelist
        return bool(pricelist) and bool(public_pricelist) and pricelist != public_pricelist

    def _int_portal_credit(self):
        """Credit snapshot for this user's company, or False when it must stay hidden.

        Figures match the partner form: open receivables (``credit``) plus confirmed
        orders not yet invoiced (``credit_to_invoice``), in the company currency.
        A negative receivable is money on account, not negative usage.
        """
        self.ensure_one()
        company = self._int_portal_company()
        if not self._int_portal_can_view_credit(company):
            return False
        if not company.sudo().account_use_credit_limit:
            return False
        commercial = self.partner_id.commercial_partner_id.sudo().with_company(company)
        limit = commercial.credit_limit or 0.0
        if limit <= 0:
            return False
        currency = company.currency_id
        figures = self._int_portal_credit_figures(
            commercial.credit,
            commercial.credit_to_invoice,
            limit,
            currency,
        )
        figures["other_currency"] = bool(self._int_portal_other_currency(commercial, company))
        return figures

    def _int_portal_other_currency(self, commercial, company):
        currency = company.currency_id
        domain = [
            ("company_id", "=", company.id),
            ("commercial_partner_id", "=", commercial.id),
            ("currency_id", "!=", currency.id),
        ]
        invoice = self.env["account.move"].sudo().search(
            domain + [("state", "=", "posted"), ("move_type", "in", ("out_invoice", "out_refund"))],
            limit=1,
        )
        if invoice:
            return True
        order = self.env["sale.order"].sudo().search(
            [
                ("company_id", "=", company.id),
                ("partner_id.commercial_partner_id", "=", commercial.id),
                ("state", "=", "sale"),
                ("currency_id", "!=", currency.id),
            ],
            limit=1,
        )
        return bool(order)

    @staticmethod
    def _int_portal_credit_figures(credit, credit_to_invoice, limit, currency):
        credit_on_account = currency.round(-credit) if credit < 0 else 0.0
        used = currency.round(max(credit, 0.0) + max(credit_to_invoice or 0.0, 0.0))
        limit = currency.round(limit)
        over = currency.round(used - limit) if used > limit else 0.0
        available = currency.round(max(limit - used, 0.0))
        ratio = (used / limit) if limit else 0.0
        if ratio < 0.75:
            level = "ok"
        elif ratio <= 0.90:
            level = "warn"
        else:
            level = "over"
        return {
            "limit": limit,
            "used": used,
            "available": available,
            "over": over,
            "credit_on_account": credit_on_account,
            "ratio": ratio,
            "percent": min(ratio * 100.0, 100.0),
            "level": level,
            "currency": currency,
        }
