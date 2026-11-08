from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.int_helpdesk_customizations.models.help_feedback import HELP_KINDS


class IntHelpdeskHelp(http.Controller):

    def _company(self):
        return request.env.user._int_help_request_company()

    def _hidden_redirect(self):
        if request.env.user._int_help_hub_visible():
            return None
        return request.redirect("/my?int_help_warning=1")

    @http.route("/my/help", type="http", auth="user", website=True, methods=["GET"], sitemap=False)
    def hub(self, **kwargs):
        hidden = self._hidden_redirect()
        if hidden:
            return hidden
        return request.render("int_helpdesk_customizations.portal_help_hub", {})

    @http.route(
        "/my/help/order-lines/<int:order_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def order_lines(self, order_id, **kwargs):
        if not request.env.user._int_help_hub_visible():
            return request.make_json_response({"error": "unavailable"}, status=403)
        lines = request.env["helpdesk.ticket"]._int_help_order_line_options(
            request.env.user, self._company(), order_id,
        )
        return request.make_json_response({"lines": lines})

    @http.route(
        "/my/help/submitted/<int:ticket_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def submitted(self, ticket_id, **kwargs):
        hidden = self._hidden_redirect()
        if hidden:
            return hidden
        Ticket = request.env["helpdesk.ticket"]
        ticket = Ticket._int_help_user_ticket(request.env.user, self._company(), ticket_id)
        if not ticket:
            return request.redirect("/my/help")
        return request.render("int_helpdesk_customizations.portal_help_done", {
            "ticket_id": ticket.id,
            "ticket_reference": Ticket._int_help_reference(ticket),
        })

    @http.route(
        "/my/help/<string:kind>",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        sitemap=False,
    )
    def form(self, kind, **post):
        if kind not in HELP_KINDS:
            raise NotFound()
        hidden = self._hidden_redirect()
        if hidden:
            return hidden
        Ticket = request.env["helpdesk.ticket"]
        company = self._company()
        prepared = Ticket._int_help_prepare(request.env.user, company, kind)
        error = None
        values = {}
        if request.httprequest.method == "POST" and not prepared["notice"]:
            values = {
                key: value for key, value in post.items() if key != "attachments"
            }
            files = request.httprequest.files.getlist("attachments")
            result = Ticket._int_help_submit(
                request.env.user, company, kind, values, files,
            )
            if result.get("ticket"):
                return request.redirect(f"/my/help/submitted/{result['ticket'].id}")
            error = result.get("error")
        return request.render("int_helpdesk_customizations.portal_help_form", {
            "error": error,
            "values": values,
            **prepared,
        })
