from odoo import api, models
from odoo.fields import Command

REPLY_TO = "info@rvsolarandbattery.com"


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._int_help_stamp_contact_tags(vals)
        return super().create(vals_list)

    @api.model
    def _int_help_stamp_contact_tags(self, vals):
        """Copy the contact's tags onto the ticket, using the same names.

        This does not look at the pricelist. A ticket with no customer is left alone.
        """
        if not vals.get("partner_id"):
            return
        partner = self.env["res.partner"].browse(vals["partner_id"]).sudo()
        categories = partner.category_id | partner.commercial_partner_id.category_id
        names = [name for name in categories.mapped("name") if name]
        if not names:
            return
        commands = list(vals.get("tag_ids") or [])
        present = self._int_help_tag_ids_in_commands(commands)
        Tag = self.env["helpdesk.tag"].sudo()
        for name in dict.fromkeys(names):
            tag = Tag.search([("name", "=", name)], order="id", limit=1)
            if not tag:
                tag = Tag.create({"name": name})
            if tag.id in present:
                continue
            self._int_help_add_tag_command(commands, tag)
            present.add(tag.id)
        vals["tag_ids"] = commands

    @api.model
    def _int_help_tag_ids_in_commands(self, commands):
        present = set()
        for command in commands:
            if not command:
                continue
            operation = command[0]
            if operation == Command.LINK and command[1]:
                present.add(command[1])
            elif operation == Command.SET:
                present.update(command[2] or ())
        return present

    @api.model
    def _int_help_add_tag_command(self, commands, tag):
        if len(commands) == 1 and commands[0] and commands[0][0] == Command.SET:
            ids = list(commands[0][2] or [])
            if tag.id not in ids:
                ids.append(tag.id)
            commands[0] = Command.set(ids)
            return
        commands.append(Command.link(tag.id))

    def _notify_get_reply_to(self, default=None, author_id=False):
        res = super()._notify_get_reply_to(default=default, author_id=author_id)
        for ticket in self.filtered(lambda t: not t.team_id.alias_email):
            res[ticket.id] = self._notify_get_reply_to_formatted_email(
                REPLY_TO, author_id=author_id,
            )
        return res
