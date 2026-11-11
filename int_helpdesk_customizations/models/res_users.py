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

    def _int_help_hub_visible(self):
        """Whether My Portal should show Help & Feedback for this user.

        Any logged-in user (staff, dealer or retail) sees it once every request
        type has an existing team. Public users never do. A missing team hides
        the hub and logs a warning instead of raising.
        """
        self.ensure_one()
        if self._is_public():
            return False
        company = self._int_help_request_company()
        if not company._int_help_ready():
            return False
        return bool(self.has_group("base.group_user") or self.has_group("base.group_portal"))

    def _int_help_kind_allowed(self, kind, company=None):
        """Whether this user may use one Help & Feedback form.

        Staff and dealers get every form. Retail users get a form when its
        ``retail`` flag in HELP_KINDS is True, so one form can be hidden from
        retail by flipping that flag.
        """
        from odoo.addons.int_helpdesk_customizations.models.help_feedback import HELP_KINDS

        self.ensure_one()
        spec = HELP_KINDS.get(kind)
        if not spec or not self._int_help_hub_visible():
            return False
        if self.has_group("base.group_user"):
            return True
        if self._int_help_is_approved_dealer(company):
            return True
        return bool(spec.get("retail"))
