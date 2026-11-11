from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.int_helpdesk_customizations.models.help_feedback import HELP_KINDS

# Tickets a guest submitted in this browser, so they can see their confirmation page.
GUEST_SESSION_KEY = "int_help_guest_tickets"


class IntHelpdeskHelp(http.Controller):
    """Help & Feedback, the site's helpdesk at /help, open to everyone.

    Guests type their contact details and order number. Logged-in users also
    get their orders, open returns and sales rep.
    """

    def _company(self):
        return request.env.user._int_help_request_company()

    def _hidden_redirect(self):
        if request.env.user._int_help_hub_visible():
            return None
        return request.redirect("/")

    @http.route("/help", type="http", auth="public", website=True, methods=["GET"], sitemap=True)
    def hub(self, **kwargs):
        hidden = self._hidden_redirect()
        if hidden:
            return hidden
        return request.render("int_helpdesk_customizations.portal_help_hub", {})

    @http.route(
        "/help/order-lines/<int:order_id>",
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
        "/help/submitted/<int:ticket_id>",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def submitted(self, ticket_id, **kwargs):
        hidden = self._hidden_redirect()
        if hidden:
            return hidden
        Ticket = request.env["helpdesk.ticket"]
        user = request.env.user
        if user._is_public():
            # Only a ticket this browser just submitted.
            ids = request.session.get(GUEST_SESSION_KEY) or []
            ticket = Ticket.sudo().browse(ticket_id).exists() if ticket_id in ids else Ticket
        else:
            ticket = Ticket._int_help_user_ticket(user, self._company(), ticket_id)
        if not ticket:
            return request.redirect("/help")
        return request.render("int_helpdesk_customizations.portal_help_done", {
            "ticket_id": ticket.id,
            "ticket_reference": Ticket._int_help_reference(ticket),
        })

    @http.route("/help/return", type="http", auth="public", website=True, methods=["GET"], sitemap=False)
    def returns(self, **kwargs):
        """Open returns, with a button to start a new one. Guests go straight to the form."""
        hidden = self._hidden_redirect()
        if hidden:
            return hidden
        if request.env.user._is_public():
            return request.redirect("/help/return/new")
        tickets = request.env["helpdesk.ticket"]._int_help_open_returns(request.env.user, self._company())
        return request.render("int_helpdesk_customizations.portal_help_returns", {
            "tickets": tickets,
        })

    @http.route(
        "/help/return/new",
        type="http",
        auth="public",
        website=True,
        methods=["GET", "POST"],
        sitemap=False,
    )
    def return_form(self, **post):
        return self._form("return", post)

    @http.route(
        "/help/<string:kind>",
        type="http",
        auth="public",
        website=True,
        methods=["GET", "POST"],
        sitemap=False,
    )
    def form(self, kind, **post):
        if kind == "return":
            return request.redirect("/help/return/new")
        if kind not in HELP_KINDS:
            raise NotFound()
        return self._form(kind, post)

    # The old portal addresses, kept for bookmarks and emails already sent.
    @http.route(
        ["/my/help", "/my/help/<path:rest>"],
        type="http",
        auth="public",
        website=True,
        methods=["GET", "POST"],
        sitemap=False,
    )
    def old_portal_address(self, rest="", **kwargs):
        return request.redirect(f"/help/{rest}" if rest else "/help", code=301)

    def _form(self, kind, post):
        hidden = self._hidden_redirect()
        if hidden:
            return hidden
        if not request.env.user._int_help_kind_allowed(kind, self._company()):
            return request.redirect("/help")
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
                ip=request.httprequest.remote_addr,
            )
            if result.get("ticket"):
                ticket = result["ticket"]
                if request.env.user._is_public():
                    ids = list(request.session.get(GUEST_SESSION_KEY) or [])[-19:]
                    request.session[GUEST_SESSION_KEY] = ids + [ticket.id]
                return request.redirect(f"/help/submitted/{ticket.id}")
            error = result.get("error")
        return request.render("int_helpdesk_customizations.portal_help_form", {
            "error": error,
            "values": values,
            **prepared,
        })
