from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _int_help_is_approved_dealer(self, company):
        """True when this contact's company pricelist is set and is not the public one.

        Pending applicants stay on the public user's pricelist, so they are not dealers.
        The public partner is never a dealer. The website module is not imported.
        """
        self.ensure_one()
        partner = self.sudo().commercial_partner_id
        if not partner:
            return False
        public_partner = self.sudo().env.ref("base.public_user").partner_id.commercial_partner_id
        if partner == public_partner:
            return False
        pricelist = partner.with_company(company).property_product_pricelist
        public_pricelist = public_partner.with_company(company).property_product_pricelist
        return bool(pricelist) and bool(public_pricelist) and pricelist != public_pricelist
