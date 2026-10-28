from odoo import api, models
from odoo.tools.mail import unfold_references


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    @api.model
    def message_route(self, message, message_dict, model=None, thread_id=None, custom_values=None):
        route = self._int_helpdesk_reply_route(message, message_dict)
        if route:
            self._routing_reset_bounce(message, message_dict)
            return [route]
        return super().message_route(
            message, message_dict, model=model, thread_id=thread_id, custom_values=custom_values,
        )

    @api.model
    def _int_helpdesk_reply_route(self, message, message_dict):
        # Odoo treats a reply sent to another model's alias (info@ creates
        # leads) as a new document. Replies to a ticket belong on the ticket.
        if message_dict.get("is_bounce"):
            return None
        references = message_dict.get("references") or message_dict.get("in_reply_to")
        if not references:
            return None
        refs = [r.strip() for r in unfold_references(references) if "reply_to" not in r][-32:]
        if not refs:
            return None
        parent = self.env["mail.message"].sudo().search(
            [("message_id", "in", refs)], limit=1, order="id desc",
        )
        if parent.model != "helpdesk.ticket" or not parent.res_id:
            return None
        user_id = self._mail_find_user_for_gateway(message_dict["email_from"]).id or self.env.uid
        return self._routing_check_route(
            message, message_dict,
            ("helpdesk.ticket", parent.res_id, None, user_id, self.env["mail.alias"]),
            raise_exception=False,
        ) or None
