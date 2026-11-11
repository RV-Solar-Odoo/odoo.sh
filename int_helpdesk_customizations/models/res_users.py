from odoo import models
from odoo.http import request


class ResUsers(models.Model):
    _inherit = "res.users"

    def _int_help_request_company(self):
        """Website company when this is a website request, otherwise the current company."""
        website = None
        try:
            if request and getattr(request, "website", None):
                website = request.website
        except RuntimeError:
            website = None
        if website and website.company_id:
            return website.company_id
        return self.env.company

    def _int_help_is_approved_dealer(self, company=None):
        self.ensure_one()
        if self._is_public():
            return False
        company = company or self._int_help_request_company()
        return self.partner_id._int_help_is_approved_dealer(company)

    def _int_help_hub_visible(self, company=None):
        """Whether Help & Feedback is open. It is the site's helpdesk, for everyone:
        guests, customers, dealers and staff, once every request type has an
        existing team. A missing team hides it and logs a warning instead of raising.
        """
        self.ensure_one()
        company = company or self._int_help_request_company()
        return bool(company._int_help_ready())

    def _int_help_kind_allowed(self, kind, company=None):
        """Whether this user may use one Help & Feedback form.

        Staff and dealers get every form. Logged-in customers get a form when its
        ``retail`` flag in HELP_KINDS is True, guests when its ``public`` flag is,
        so one form can be hidden from either group by flipping that flag.
        """
        from odoo.addons.int_helpdesk_customizations.models.help_feedback import HELP_KINDS

        self.ensure_one()
        spec = HELP_KINDS.get(kind)
        company = company or self._int_help_request_company()
        if not spec or not self._int_help_hub_visible(company):
            return False
        if self._is_public():
            return bool(spec.get("public"))
        if self.has_group("base.group_user"):
            return True
        if self._int_help_is_approved_dealer(company):
            return True
        return bool(spec.get("retail"))
