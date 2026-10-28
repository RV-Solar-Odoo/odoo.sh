from odoo import models

# info@ already belongs to the Dealership Applications sales team, which turns
# mail sent there into leads. Helpdesk must not take that alias. This only
# changes the Reply-To header on ticket emails.
REPLY_TO = "info@rvsolarandbattery.com"


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def _notify_get_reply_to(self, default=None, author_id=False):
        res = super()._notify_get_reply_to(default=default, author_id=author_id)
        for ticket in self:
            res[ticket.id] = self._notify_get_reply_to_formatted_email(
                REPLY_TO, author_id=author_id,
            )
        return res
