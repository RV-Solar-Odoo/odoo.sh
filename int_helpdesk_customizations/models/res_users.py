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

        Public users never see it. Internal users see it when every request
        type has an existing team, so staff can test. Portal users see it only
        as approved dealers, and only when those teams are set. A missing team
        hides the hub and logs a warning instead of raising.
        """
        self.ensure_one()
        if self._is_public():
            return False
        company = self._int_help_request_company()
        if not company._int_help_ready():
            return False
        if self.has_group("base.group_user"):
            return True
        return bool(
            self.has_group("base.group_portal")
            and self._int_help_is_approved_dealer(company)
        )
