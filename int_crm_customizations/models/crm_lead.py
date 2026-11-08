from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import email_normalize, format_date

from .res_partner import TAX_EXEMPTION_REASONS

EXEMPT_FISCAL_POSITION = "Wholesale — tax exempt"
GRANT_GROUPS = ("sales_team.group_sale_manager", "account.group_account_invoice")


class CrmLead(models.Model):
    _inherit = "crm.lead"

    x_is_tax_exempt = fields.Boolean(string="Tax Exempt?", default=False)
    x_tax_exemption_reason = fields.Selection(
        TAX_EXEMPTION_REASONS,
        string="Tax Exemption Reason",
        compute="_compute_x_tax_exemption_reason",
        store=True,
        readonly=False,
    )
    x_tax_exemption_document = fields.Binary(string="Tax Exemption Certificate", attachment=True)
    x_tax_exemption_document_filename = fields.Char()
    x_tax_exemption_approved = fields.Boolean(
        string="Exemption Approved",
        compute="_compute_x_tax_exemption_approved",
        store=True,
        readonly=True,
        copy=False,
    )

    @api.depends("x_is_tax_exempt")
    def _compute_x_tax_exemption_reason(self):
        for lead in self:
            if not lead.x_is_tax_exempt:
                lead.x_tax_exemption_reason = False

    @api.depends("x_is_tax_exempt")
    def _compute_x_tax_exemption_approved(self):
        # A readonly compute can't fall back on the stored value in the form, so read it from _origin.
        for lead in self:
            lead.x_tax_exemption_approved = lead.x_is_tax_exempt and lead._origin.x_tax_exemption_approved

    def _int_check_can_approve(self, vals):
        # Readonly only binds the form, and approval removes tax, so check the write too.
        if not vals.get("x_tax_exemption_approved") or self.env.su:
            return
        if not any(self.env.user.has_group(group) for group in GRANT_GROUPS):
            raise AccessError(self.env._("Only sales administrators and invoicing users can grant a tax exemption."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._int_check_can_approve(vals)
        leads = super().create(vals_list)
        for lead in leads.filtered("x_tax_exemption_approved"):
            lead._int_apply_tax_exemption()
        return leads

    def write(self, vals):
        self._int_check_can_approve(vals)
        if "partner_id" not in vals and "x_tax_exemption_approved" not in vals:
            return super().write(vals)
        # Conversion and linking a contact both arrive here. Comparing with the old values
        # means a repeat write can't overwrite what accounting has since changed on the contact.
        before = {lead.id: (lead.x_tax_exemption_approved, lead.partner_id.id) for lead in self}
        res = super().write(vals)
        for lead in self.filtered("x_tax_exemption_approved"):
            if before[lead.id] != (True, lead.partner_id.id):
                lead._int_apply_tax_exemption()
        return res

    def _int_tax_exemption_reason_label(self):
        self.ensure_one()
        field = self._fields["x_tax_exemption_reason"]
        return dict(field._description_selection(self.env)).get(self.x_tax_exemption_reason)

    def action_int_send_dealer_account_email(self):
        """Send the account email for this application.

        If the email already has a portal login, the application is linked to that
        contact so a checkout account and a later dealer application stay one login.
        """
        self.ensure_one()
        partner = self._int_account_partner()
        if self.partner_id != partner:
            self.partner_id = partner
            self.message_post(
                body=self.env._(
                    "Linked this application to %(name)s because %(email)s already has a portal login.",
                    name=partner.display_name,
                    email=partner.email,
                ),
                subtype_xmlid="mail.mt_note",
            )
        return partner.action_int_send_dealer_account_email()

    def _int_account_partner(self):
        self.ensure_one()
        email = email_normalize(self.email_from or self.partner_id.email or "")
        if not email:
            raise UserError(self.env._("Add an email, or link a contact, before sending the account email."))
        partners = self.env["res.partner"].search([("email_normalized", "=", email)])
        if self.partner_id:
            family = self.partner_id.commercial_partner_id | self.partner_id.commercial_partner_id.child_ids
            owned = (partners & family).filtered(
                lambda partner: partner.with_context(active_test=False).user_ids
            )
            if owned:
                return owned[:1]
        with_login = partners.filtered(lambda partner: partner.with_context(active_test=False).user_ids)
        if with_login:
            return with_login[:1]
        if self.partner_id:
            return self.partner_id
        if partners:
            return partners[:1]
        return self.env["res.partner"].create({
            "name": self.contact_name or self.partner_name or self.name,
            "email": email,
            "company_id": self.company_id.id,
        })

    def action_grant_tax_exemption(self):
        self._int_check_can_approve({"x_tax_exemption_approved": True})
        for lead in self:
            if not lead.x_is_tax_exempt:
                raise UserError(self.env._("Tick Tax Exempt? before granting the exemption."))
            if not lead.x_tax_exemption_reason:
                raise UserError(self.env._("Choose a Tax Exemption Reason before granting the exemption."))
            if not lead.x_tax_exemption_document:
                raise UserError(self.env._("Add the Tax Exemption Certificate before granting the exemption."))
            lead.write({"x_tax_exemption_approved": True})
            lead.message_post(
                body=self.env._(
                    "Tax exemption approved by %(user)s on %(date)s (%(reason)s)",
                    user=self.env.user.name,
                    date=format_date(self.env, fields.Date.context_today(lead)),
                    reason=lead._int_tax_exemption_reason_label(),
                ),
                subtype_xmlid="mail.mt_note",
            )
        return True

    def _int_apply_tax_exemption(self):
        """Copy an approved exemption to the customer's company, which syncs its child contacts."""
        self.ensure_one()
        target = self.sudo().partner_id.commercial_partner_id
        if not target:
            return
        company = self.company_id or self.env.company
        positions = self.env["account.fiscal.position"].sudo()
        position = positions.search([
            ("name", "=", EXEMPT_FISCAL_POSITION),
            *positions._check_company_domain(company),
        ], limit=1)
        if not position:
            raise UserError(self.env._(
                'The fiscal position "%(name)s" does not exist. Create it in Accounting, then try again.',
                name=EXEMPT_FISCAL_POSITION,
            ))
        # A form call can carry bin_size, which would copy the file's size in place of the file.
        lead = self.sudo().with_context(bin_size=False)
        target.with_company(company).write({
            "x_is_tax_exempt": True,
            "x_tax_exemption_reason": lead.x_tax_exemption_reason,
            "x_tax_exemption_document": lead.x_tax_exemption_document,
            "x_tax_exemption_document_filename": lead.x_tax_exemption_document_filename,
            "property_account_position_id": position.id,
        })
        target.message_post(
            body=self.env._(
                "Tax exemption applied from %(lead)s (%(reason)s). Fiscal position set to %(position)s.",
                lead=self.name,
                reason=self._int_tax_exemption_reason_label(),
                position=position.name,
            ),
            subtype_xmlid="mail.mt_note",
        )
