from odoo import api, models
from odoo.fields import Command

REPLY_TO = "info@rvsolarandbattery.com"
TAG_CUSTOMER_DEALER = "int_helpdesk_customizations.tag_customer_dealer"
TAG_CUSTOMER_RETAIL = "int_helpdesk_customizations.tag_customer_retail"


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._int_help_stamp_customer_type(vals)
        return super().create(vals_list)

    @api.model
    def _int_help_stamp_customer_type(self, vals):
        """Add Customer type: Dealer or Customer type: Retail when the ticket has a customer.

        A tag already present in the create commands is left as it is.
        """
        if not vals.get("partner_id"):
            return
        dealer_tag = self.env.ref(TAG_CUSTOMER_DEALER, raise_if_not_found=False)
        retail_tag = self.env.ref(TAG_CUSTOMER_RETAIL, raise_if_not_found=False)
        if not dealer_tag or not retail_tag:
            return
        known = {dealer_tag.id, retail_tag.id}
        commands = list(vals.get("tag_ids") or [])
        if self._int_help_commands_have_tag(commands, known):
            return
        company = self._int_help_company_for_vals(vals)
        partner = self.env["res.partner"].browse(vals["partner_id"])
        tag = dealer_tag if partner._int_help_is_approved_dealer(company) else retail_tag
        if len(commands) == 1 and commands[0] and commands[0][0] == Command.SET:
            ids = commands[0][2]
            if tag.id not in ids:
                ids.append(tag.id)
            return
        commands.append(Command.link(tag.id))
        vals["tag_ids"] = commands

    @api.model
    def _int_help_commands_have_tag(self, commands, tag_ids):
        for command in commands:
            if not command:
                continue
            operation = command[0]
            if operation == Command.LINK and command[1] in tag_ids:
                return True
            if operation == Command.SET and tag_ids.intersection(command[2] or ()):
                return True
        return False

    @api.model
    def _int_help_company_for_vals(self, vals):
        if vals.get("company_id"):
            return self.env["res.company"].browse(vals["company_id"])
        if vals.get("team_id"):
            team = self.env["helpdesk.team"].browse(vals["team_id"])
            if team.company_id:
                return team.company_id
        return self.env.company

    def _notify_get_reply_to(self, default=None, author_id=False):
        res = super()._notify_get_reply_to(default=default, author_id=author_id)
        for ticket in self.filtered(lambda t: not t.team_id.alias_email):
            res[ticket.id] = self._notify_get_reply_to_formatted_email(
                REPLY_TO, author_id=author_id,
            )
        return res
