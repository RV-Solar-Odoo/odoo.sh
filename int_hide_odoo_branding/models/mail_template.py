from odoo import api, fields, models

SIGNATURE_LAYOUT = "int_hide_odoo_branding.mail_notification_signature_only"


class MailTemplate(models.Model):
    _inherit = "mail.template"

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if not values.get("email_layout_xmlid"):
                values["email_layout_xmlid"] = SIGNATURE_LAYOUT
        return super().create(vals_list)

    # A checkbox, not the layout's name: Odoo sends a blank email if that name is mistyped.
    int_add_company_signature = fields.Boolean(
        string="Add Company Signature",
        compute="_compute_int_add_company_signature",
        inverse="_inverse_int_add_company_signature",
        help="Adds the company signature below this email when it's sent directly, "
             "like from an automation rule sending as Email.",
    )

    @api.depends("email_layout_xmlid")
    def _compute_int_add_company_signature(self):
        for template in self:
            template.int_add_company_signature = template.email_layout_xmlid == SIGNATURE_LAYOUT

    def _inverse_int_add_company_signature(self):
        for template in self:
            if template.int_add_company_signature:
                template.email_layout_xmlid = SIGNATURE_LAYOUT
            elif template.email_layout_xmlid == SIGNATURE_LAYOUT:
                template.email_layout_xmlid = False
