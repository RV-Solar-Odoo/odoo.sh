import logging

from odoo import fields, models
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rvsb_create_account = fields.Boolean(
        string="Account Requested",
        copy=False,
        help="The guest ticked 'Create an account' at checkout.",
    )
    rvsb_account_status = fields.Selection(
        selection=[
            ('invited', "Activation email sent"),
            ('exists', "Email already had an account"),
            ('failed', "Could not create account"),
        ],
        string="Account Request",
        copy=False,
        readonly=True,
    )

    def write(self, vals):
        res = super().write(vals)
        # 'sent' = order placed with a pending payment (e.g. wire transfer),
        # 'sale' = order confirmed. Either way the checkout is finished.
        if vals.get('state') in ('sent', 'sale'):
            self.filtered(
                lambda so: so.rvsb_create_account and not so.rvsb_account_status
            )._rvsb_invite_customer()
        return res

    def _rvsb_invite_customer(self):
        """Create a password-less portal user for the order's customer and email them
        the link to set a password. Never blocks the order: any failure is logged."""
        template = self.env.ref(
            'rvsb_checkout_account.mail_template_account_activation', raise_if_not_found=False
        )
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        for order in self.sudo():
            partner = order.partner_id
            email = email_normalize(partner.email or '')
            status = 'failed'
            try:
                with self.env.cr.savepoint():
                    if not email:
                        raise ValueError("no valid email on %s" % partner.display_name)
                    if partner.user_ids or Users.search_count(Users._get_login_domain(email), limit=1):
                        status = 'exists'
                    else:
                        company = order.company_id
                        values = {
                            'login': email,
                            'email': email,
                            'partner_id': partner.id,
                            'company_id': company.id,
                            'company_ids': [(6, 0, company.ids)],
                        }
                        if order.website_id.specific_user_account:
                            values['website_id'] = order.website_id.id
                        user = Users.with_company(company)._create_user_from_template(values)
                        partner.signup_prepare()
                        if template:
                            template.sudo().with_context(
                                lang=partner.lang, rvsb_order_name=order.name,
                            ).send_mail(user.id, force_send=True)
                        status = 'invited'
            except Exception:
                _logger.exception("Checkout account request failed for order %s", order.name)
                status = 'failed'
            order.rvsb_account_status = status
