from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    int_quote_price_basis = fields.Selection(
        [("map", "MAP"), ("msrp", "MSRP")],
        string="Customer quote price",
        default="map",
        help="The starting price on this dealer's customer quotes. MAP or MSRP, never the wholesale price.",
    )

    def write(self, vals):
        if "int_quote_price_basis" in vals and not self.env.su and not self.env.user.has_group("base.group_user"):
            raise AccessError(_("Only the account owner can change customer quote prices."))
        if vals.get("int_quote_price_basis") not in (None, "map", "msrp"):
            raise UserError(_("Choose MAP or MSRP."))
        return super().write(vals)

    @api.model
    def _int_set_quote_basis(self, user, basis):
        """Portal owners set the company default. Staff use the contact form."""
        if basis not in ("map", "msrp"):
            raise UserError(_("Choose MAP or MSRP."))
        if not user or not user.share or not user.int_portal_can("manage_users"):
            raise UserError(_("Only the account owner can change customer quote prices."))
        commercial = user.partner_id.commercial_partner_id
        commercial.sudo().write({"int_quote_price_basis": basis})
        return commercial
