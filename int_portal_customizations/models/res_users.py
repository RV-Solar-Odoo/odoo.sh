from odoo import models
from odoo.tools.image import image_data_uri

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

    def _int_portal_can_view_credit(self):
        """Owner, Accountant, and internal users. Buyer and Viewer cannot."""
        self.ensure_one()
        if self._is_public():
            return False
        if self.has_group("base.group_user"):
            return True
        role = self.partner_id.sudo().int_portal_role or "owner"
        return role in CREDIT_ROLES

    def _int_portal_sales_rep(self):
        """The commercial partner's salesperson, or False when none is assigned."""
        self.ensure_one()
        if self._is_public():
            return False
        commercial = self.partner_id.commercial_partner_id
        rep_user = commercial.user_id
        if not rep_user:
            return False
        rep = rep_user.partner_id.sudo()
        phone = False
        for field_name in ("work_phone", "phone", "mobile"):
            if field_name in rep._fields and rep[field_name]:
                phone = rep[field_name]
                break
        digits = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
        image = rep.avatar_128
        return {
            "name": rep.name or rep_user.name,
            "email": rep.email or rep_user.email or False,
            "phone": phone or False,
            "phone_href": f"tel:{digits}" if digits else False,
            "image": image_data_uri(image) if image else False,
        }

    def _int_portal_credit(self):
        """Credit snapshot for this user's company, or False when it must stay hidden.

        Figures match the partner form: open receivables (``credit``) plus confirmed
        orders not yet invoiced (``credit_to_invoice``), in the company currency.
        A negative receivable is money on account, not negative usage.
        """
        self.ensure_one()
        if not self._int_portal_can_view_credit():
            return False
        company = self._int_portal_company()
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
