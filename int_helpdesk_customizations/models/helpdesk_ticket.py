from odoo import models

REPLY_TO = "info@rvsolarandbattery.com"


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def _notify_get_reply_to(self, default=None, author_id=False):
        res = super()._notify_get_reply_to(default=default, author_id=author_id)
        for ticket in self.filtered(lambda t: not t.team_id.alias_email):
            res[ticket.id] = self._notify_get_reply_to_formatted_email(
                REPLY_TO, author_id=author_id,
            )
        return res
