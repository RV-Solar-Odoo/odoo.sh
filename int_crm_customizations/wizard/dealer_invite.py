from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize

# Credit limit choices on Create Dealer Account. Edit this list to change them:
# (key, label, amount). "none" leaves the contact alone; "other" asks for an amount.
CREDIT_LIMIT_CHOICES = [
    ("none", "No limit", 0.0),
    ("1000", "$1,000", 1000.0),
    ("3000", "$3,000", 3000.0),
    ("5000", "$5,000", 5000.0),
    ("10000", "$10,000", 10000.0),
    ("other", "Other", 0.0),
]


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
    credit_limit_choice = fields.Selection(
        [(key, label) for key, label, _amount in CREDIT_LIMIT_CHOICES],
        string="Credit limit",
        required=True,
        default="none",
    )
    credit_limit_other = fields.Monetary(string="Credit limit amount", currency_field="currency_id")
    currency_id = fields.Many2one(related="company_id.currency_id")

    @api.constrains("credit_limit_choice", "credit_limit_other")
    def _check_credit_limit_other(self):
        for wizard in self:
            if wizard.credit_limit_choice == "other" and (wizard.credit_limit_other or 0.0) <= 0:
                raise ValidationError(_("Enter a credit limit amount greater than zero."))

    def _credit_limit_amount(self):
        """The chosen limit, or 0.0 for No limit."""
        self.ensure_one()
        if self.credit_limit_choice == "other":
            return self.credit_limit_other or 0.0
        amounts = {key: amount for key, _label, amount in CREDIT_LIMIT_CHOICES}
        return amounts.get(self.credit_limit_choice, 0.0)

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
        limit = self._credit_limit_amount()
        if limit > 0:
            commercial.sudo().with_company(self.company_id).write({
                "credit_limit": limit,
                "use_partner_credit_limit": True,
            })
        _title, message, level = partner._int_dealer_account_email_notice(code, user, owner)
        notice = _(
            "%(message)s Pricelist on %(name)s is now %(pricelist)s. Tagged RVSB Dealer.",
            message=message,
            name=commercial.display_name,
            pricelist=self.pricelist_id.display_name,
        )
        if limit > 0:
            notice = _(
                "%(notice)s Credit limit set to %(limit)s.",
                notice=notice,
                limit=self.company_id.currency_id.format(limit),
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
