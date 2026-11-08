from odoo import _, api, fields, models
from odoo.tools import email_normalize


class IntDealerInvite(models.TransientModel):
    _name = "int.dealer.invite"
    _description = "Invite a dealer"

    lead_id = fields.Many2one("crm.lead", required=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", required=True)
    who = fields.Char(string="Contact", compute="_compute_who")
    email = fields.Char(compute="_compute_email")
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Pricelist",
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )

    @api.depends("lead_id.contact_name", "lead_id.partner_name", "lead_id.partner_id", "lead_id.name")
    def _compute_who(self):
        for wizard in self:
            lead = wizard.lead_id
            wizard.who = (
                lead.contact_name
                or lead.partner_name
                or lead.partner_id.display_name
                or lead.name
                or ""
            )

    @api.depends("lead_id.email_from", "lead_id.partner_id.email")
    def _compute_email(self):
        for wizard in self:
            lead = wizard.lead_id
            wizard.email = email_normalize(lead.email_from or lead.partner_id.email or "") or ""

    def action_confirm(self):
        """Set the pricelist and RVSB Dealer tag, then send the account email."""
        self.ensure_one()
        lead = self.lead_id
        partner = lead._int_account_partner()
        if lead.partner_id != partner:
            lead.partner_id = partner
            lead.message_post(
                body=self.env._(
                    "Linked this application to %(name)s because %(email)s already has a portal login.",
                    name=partner.display_name,
                    email=partner.email,
                ),
                subtype_xmlid="mail.mt_note",
            )
        partner._int_check_dealer_account_email_access()
        code, user, owner = partner._int_send_dealer_account_email()
        commercial = owner._int_apply_dealer_pricelist_and_tag(self.pricelist_id, self.company_id)
        _title, message, level = partner._int_dealer_account_email_notice(code, user, owner)
        notice = _(
            "%(message)s Pricelist on %(name)s is now %(pricelist)s. Tagged RVSB Dealer.",
            message=message,
            name=commercial.display_name,
            pricelist=self.pricelist_id.display_name,
        )
        noted = self.env["res.partner"]
        for record in (commercial, owner, partner):
            if record not in noted:
                record.message_post(body=notice, subtype_xmlid="mail.mt_note")
                noted |= record
        lead.message_post(body=notice, subtype_xmlid="mail.mt_note")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Dealer invite sent"),
                "message": notice,
                "type": level,
                "sticky": level == "warning",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
