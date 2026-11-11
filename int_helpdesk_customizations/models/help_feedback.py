import base64
import hashlib
import logging
import math
import os
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.fields import Command
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DUPLICATE_WINDOW = timedelta(seconds=60)
# Picked in the return form's order list, or sent when the dealer has no orders:
# the order number and product are typed instead of chosen.
TYPED_ORDER = "typed"
EN_DASH = "\u2013"

IMAGE_TYPES = {
    "jpg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    "jpeg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    "png": {"image/png"},
    "gif": {"image/gif"},
    "webp": {"image/webp"},
}
VIDEO_TYPES = {
    "mp4": {"video/mp4"},
    "mov": {"video/quicktime"},
}

# Return choices are copied from the public returns form (/helpdesk, RVSB Returns)
# so both forms ask the same questions. "Product is defective" is left out: that
# is a warranty claim.
RETURN_REASONS = (
    ("wrong_product", "Ordered the wrong product"),
    ("not_needed", "No longer need it"),
    ("other", "Other"),
)
RETURN_PACKAGING = (
    ("yes", "Yes"),
    ("no", "No"),
)
RETURN_CONDITIONS = (
    ("unopened", "Unopened"),
    ("opened", "Opened"),
    ("installed", "Installed"),
)
RETURN_OUTCOMES = (
    ("refund", "Refund to Payment Method"),
    ("store_credit", "Store credit"),
    ("replacement", "Replacement"),
    ("different", "Replace with different product"),
    ("other", "Other"),
)
# "Where did you buy it?" for retail returns and warranty claims.
PURCHASE_SOURCES = (
    ("direct", "Directly from RV Solar & Battery"),
    ("dealer", "From one of our dealers"),
)
FEEDBACK_AREAS = (
    ("website", "website"),
    ("ordering", "ordering"),
    ("shipping", "shipping"),
    ("billing", "billing"),
    ("other", "other"),
)

HELP_KINDS = {
    "return": {
        "title": "Start a return",
        "name": "Return",
        "tag_field": "int_help_tag_return_id",
        "team_field": "int_help_team_return_id",
        "code": "help_return",
        # Who besides dealers and staff can use this form. Set False to hide it.
        "retail": True,  # logged-in customers who are not dealers
        "public": True,  # guests who are not logged in
        "max_files": 5,
        "allow_video": False,
        "upload_label": "Photos",
        "accept": "image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp",
    },
    "warranty": {
        "title": "Start a warranty claim",
        "name": "Warranty Claim",
        "tag_field": "int_help_tag_warranty_id",
        "team_field": "int_help_team_warranty_id",
        "code": "help_warranty",
        # Who besides dealers and staff can use this form. Set False to hide it.
        "retail": True,  # logged-in customers who are not dealers
        "public": True,  # guests who are not logged in
        "max_files": 5,
        "allow_video": True,
        "upload_label": "Photos or video",
        "accept": "image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,.jpg,.jpeg,.png,.gif,.webp,.mp4,.mov",
    },
    "feedback": {
        "title": "Website & operations feedback",
        "name": "Feedback",
        "tag_field": "int_help_tag_feedback_id",
        "team_field": "int_help_team_feedback_id",
        "code": "help_feedback",
        # Who besides dealers and staff can use this form. Set False to hide it.
        "retail": True,  # logged-in customers who are not dealers
        "public": True,  # guests who are not logged in
        "max_files": 3,
        "allow_video": False,
        "upload_label": "Screenshot",
        "accept": "image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp",
    },
    "part": {
        "title": "Request a part we don't stock",
        "name": "Part Request",
        "tag_field": "int_help_tag_part_id",
        "team_field": "int_help_team_part_id",
        "code": "help_part",
        # Who besides dealers and staff can use this form. Set False to hide it.
        "retail": True,  # logged-in customers who are not dealers
        "public": True,  # guests who are not logged in
        "max_files": 0,
        "allow_video": False,
        "upload_label": "",
        "accept": "",
    },
    "general": {
        "title": "General inquiries",
        "name": "General Inquiry",
        "tag_field": "int_help_tag_general_id",
        "team_field": "int_help_team_general_id",
        "code": "help_general",
        # Who besides dealers and staff can use this form. Set False to hide it.
        "retail": True,  # logged-in customers who are not dealers
        "public": True,  # guests who are not logged in
        "max_files": 3,
        "allow_video": False,
        "upload_label": "Attachment",
        "accept": "image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp",
    },
}
# Guests: at most this many requests per hour from one address (IP) or email.
GUEST_HOURLY_LIMIT = 10
# A hidden field people never see. A bot that fills it in is turned away.
HONEYPOT_FIELD = "int_help_website"


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    int_help_purchase_source = fields.Selection(
        list(PURCHASE_SOURCES), string="Where did you buy it?", copy=False,
    )
    int_help_purchase_dealer_id = fields.Many2one(
        "res.partner", string="Bought from dealer", copy=False, ondelete="set null",
    )
    # Guest submissions only, for the hourly limit.
    int_help_ip = fields.Char(string="Submitted from (IP)", copy=False, readonly=True)

    @api.model
    def _int_help_kind(self, kind):
        return HELP_KINDS.get(kind)

    @api.model
    def _int_help_prepare(self, user, company, kind):
        """Values the form needs."""
        spec = HELP_KINDS[kind]
        orders = self._int_help_orders(user, company)
        return {
            "kind": kind,
            "title": spec["title"],
            "orders": orders,
            "typed_order": TYPED_ORDER,
            "notice": False,
            "reasons": RETURN_REASONS,
            "packaging": RETURN_PACKAGING,
            "conditions": RETURN_CONDITIONS,
            "outcomes": RETURN_OUTCOMES,
            "areas": FEEDBACK_AREAS,
            "is_guest": user._is_public(),
            "honeypot_field": HONEYPOT_FIELD,
            "ask_purchase": kind in ("return", "warranty") and self._int_help_asks_purchase(user, company),
            "purchase_sources": PURCHASE_SOURCES,
            "dealers": self.env["res.partner"]._int_help_dealer_companies(company)
            if kind in ("return", "warranty") and self._int_help_asks_purchase(user, company)
            else self.env["res.partner"],
            "max_files": spec["max_files"],
            "accept": spec["accept"],
            "upload_label": spec["upload_label"],
        }

    @api.model
    def _int_help_submit(self, user, company, kind, data, files=None, ip=None):
        """Validate a portal submission and create the ticket.

        Returns ``{"ticket": record}`` or ``{"error": message}``. Creating the
        ticket in New sends that stage's receipt. If the stage has no template,
        a Help & Feedback receipt is sent to the email on the ticket.
        """
        spec = self._int_help_kind(kind)
        if not spec:
            return {"error": _("That request type is not available.")}
        access_error = self._int_help_access_error(user, company, kind)
        if access_error:
            return {"error": access_error}
        tag = company.sudo()[spec["tag_field"]]
        if not tag:
            _logger.warning(
                "Help & Feedback tag %s is not configured for %s.",
                spec["tag_field"], company.display_name,
            )
            return {"error": _("This request type is not set up yet.")}
        data = data or {}
        if user._is_public() and (data.get(HONEYPOT_FIELD) or "").strip():
            _logger.info("Help & Feedback turned away a submission that filled the hidden field.")
            return {"error": _("We could not send your request. Please try again.")}
        parsed, error = self._int_help_parse(user, company, kind, spec, data, files or [])
        if error:
            return {"error": error}
        if user._is_public():
            parsed["vals"]["int_help_ip"] = (ip or "")[:64] or False
            if self._int_help_guest_rate_limited(parsed["guest"]["email"], ip):
                return {"error": _("You can submit up to 10 Help & Feedback requests per hour.")}
        elif self._int_help_rate_limited(user, company):
            return {"error": _("You can submit up to 10 Help & Feedback requests per hour.")}
        team = company._int_help_team_for(kind)
        if not team:
            _logger.warning(
                "Help & Feedback team %s is not configured for %s.",
                spec["team_field"], company.display_name,
            )
            return {"error": _("This request type is not set up yet.")}
        vals = self._int_help_ticket_vals(user, company, spec, team, tag, parsed)
        self._int_help_lock_submission(user, vals["name"], vals.get("partner_email"))
        duplicate = self._int_help_recent_duplicate(user, vals)
        if duplicate:
            return {"ticket": duplicate}
        ticket = self.sudo().with_company(company).create(vals)
        self._int_help_confirm_received(ticket)
        self._int_help_store_attachments(ticket, parsed["uploads"])
        if parsed["order"] and kind in ("return", "warranty"):
            self._int_help_note_on_order(parsed["order"], ticket, user)
        self.env["int.helpdesk.alert.list"]._int_notify(
            spec["code"], ticket, ticket.name, company,
        )
        return {"ticket": ticket}

    @api.model
    def _int_help_access_error(self, user, company, kind=None):
        if not user:
            return _("Help & Feedback is not available for this account.")
        if not company._int_help_ready():
            return _("Help & Feedback is not available right now.")
        if kind and not user._int_help_kind_allowed(kind, company):
            return _("That request type is not available for this account.")
        return None

    @api.model
    def _int_help_order_domain(self, user, company):
        # Guests have no orders here: they type the order number.
        commercial = user.partner_id.sudo().commercial_partner_id
        if not commercial or user._is_public():
            return [("id", "=", 0)]
        cutoff = fields.Datetime.now() - relativedelta(months=24)
        return [
            ("company_id", "=", company.id),
            ("partner_id", "child_of", commercial.id),
            ("state", "in", ("sale", "done")),
            ("date_order", ">=", cutoff),
        ]

    @api.model
    def _int_help_orders(self, user, company):
        return self.env["sale.order"].sudo().search(
            self._int_help_order_domain(user, company),
            order="date_order desc, id desc",
        )

    @api.model
    def _int_help_own_order(self, user, company, order_id):
        if not order_id:
            return self.env["sale.order"]
        return self.env["sale.order"].sudo().search(
            self._int_help_order_domain(user, company) + [("id", "=", order_id)],
            limit=1,
        )

    @api.model
    def _int_help_order_line_options(self, user, company, order_id):
        """Products on one order that passed the ownership check. Anything else is an empty list."""
        order = self._int_help_own_order(user, company, order_id)
        serials = self._int_help_order_serials(order)
        seen = set()
        options = []
        for line in order.order_line:
            product = line.product_id
            if not self._int_help_returnable_line(line) or product.id in seen:
                continue
            seen.add(product.id)
            sku = product.default_code
            label = f"{sku} {EN_DASH} {product.name}" if sku else product.name
            options.append({
                "product_id": product.id,
                "name": label,
                "serials": serials.get(product.id, []),
            })
        return options

    @api.model
    def _int_help_order_serials(self, order):
        """Lot/serial numbers on the order's delivered moves, by product.

        Only the order that passed the ownership check is read, in one pass.
        """
        if not order or "picking_ids" not in order._fields:
            return {}
        pickings = order.sudo().picking_ids.filtered(
            lambda picking: picking.picking_type_code == "outgoing" and picking.state == "done"
        )
        serials = {}
        for move_line in pickings.move_line_ids:
            name = (move_line.lot_id.name or move_line.lot_name or "").strip()
            if not name:
                continue
            names = serials.setdefault(move_line.product_id.id, [])
            if name not in names:
                names.append(name)
        return serials

    @api.model
    def _int_help_order_product(self, order, product_id):
        if not order or not product_id:
            return self.env["product.product"]
        lines = order.order_line.filtered(
            lambda line: self._int_help_returnable_line(line) and line.product_id.id == product_id
        )
        return lines[:1].product_id

    @api.model
    def _int_help_returnable_line(self, line):
        """A physical item the dealer received. Delivery, coupon and discount,
        down payment, section and note lines, services and combo headers are not."""
        product = line.product_id
        if line.display_type or not product or product.type != "consu":
            return False
        if line.is_downpayment or line._is_delivery():
            return False
        # A free-product reward is a real item; a discount or coupon line is not.
        if "reward_id" in line._fields and line.reward_id and line.reward_id.reward_type != "product":
            return False
        return True

    @api.model
    def _int_help_lock_submission(self, user, name, email=None):
        """Serialize two identical submits so the second one sees the first ticket."""
        who = f"guest:{(email or '').lower()}" if user._is_public() else (user.partner_id.id or 0)
        digest = hashlib.sha256(f"int-help:{who}:{name}".encode()).digest()
        key = int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [key])

    @api.model
    def _int_help_recent_duplicate(self, user, vals):
        """The same request submitted again within a minute is the first ticket."""
        if not user.partner_id or not vals.get("name"):
            return self.browse()
        since = fields.Datetime.now() - DUPLICATE_WINDOW
        if user._is_public():
            if not vals.get("partner_email"):
                return self.browse()
            who = [("partner_email", "=ilike", vals["partner_email"]), ("int_help_ip", "!=", False)]
        else:
            who = [("partner_id", "=", user.partner_id.id)]
        domain = who + [
            ("name", "=", vals["name"]),
            ("create_date", ">=", since),
        ]
        if vals.get("team_id"):
            domain.append(("team_id", "=", vals["team_id"]))
        return self.sudo().search(domain, order="id desc", limit=1)

    @api.model
    def _int_help_rate_limited(self, user, company):
        tags = company._int_help_tags()
        if not tags or not user.partner_id:
            return False
        since = fields.Datetime.now() - timedelta(hours=1)
        count = self.sudo().with_context(active_test=False).search_count([
            ("partner_id", "=", user.partner_id.id),
            ("tag_ids", "in", tags.ids),
            ("create_date", ">=", since),
        ])
        return count >= 10

    @api.model
    def _int_help_guest_rate_limited(self, email, ip):
        """Guests share one login, so count by address (IP) and by email instead."""
        since = fields.Datetime.now() - timedelta(hours=1)
        Ticket = self.sudo().with_context(active_test=False)
        checks = []
        if ip:
            checks.append([("int_help_ip", "=", ip[:64])])
        if email:
            checks.append([("partner_email", "=ilike", email), ("int_help_ip", "!=", False)])
        for who in checks:
            if Ticket.search_count(who + [("create_date", ">=", since)]) >= GUEST_HOURLY_LIMIT:
                return True
        return False

    @api.model
    def _int_help_open_returns(self, user, company):
        """Open returns for everyone at the dealer's company, from either return form.

        Warranty claims go to the same team, so their tag keeps them out. A ticket
        in a folded stage is closed.
        """
        team = company._int_help_team_for("return")
        commercial = user.partner_id.sudo().commercial_partner_id
        if not team or not commercial or user._is_public():
            return self.sudo().browse()
        domain = [
            ("team_id", "=", team.id),
            ("partner_id", "child_of", commercial.id),
            ("stage_id.fold", "=", False),
        ]
        warranty_tag = company.sudo().int_help_tag_warranty_id
        if warranty_tag:
            domain.append(("tag_ids", "not in", warranty_tag.ids))
        return self.sudo().search(domain, order="create_date desc, id desc")

    @api.model
    def _int_help_reference(self, ticket):
        ticket.ensure_one()
        if "ticket_ref" in ticket._fields and ticket.ticket_ref:
            return ticket.ticket_ref
        return str(ticket.id)

    @api.model
    def _int_help_user_ticket(self, user, company, ticket_id):
        tags = company._int_help_tags()
        domain = [
            ("id", "=", ticket_id),
            ("partner_id", "=", user.partner_id.id),
        ]
        if tags:
            domain.append(("tag_ids", "in", tags.ids))
        return self.sudo().search(domain, limit=1)

    @api.model
    def _int_help_confirm_received(self, ticket):
        """Send one receipt when the New stage did not send its own."""
        if ticket.message_ids.filtered(lambda message: message.message_type == "auto_comment"):
            return
        email = (ticket.partner_email or "").strip()
        if not email:
            _logger.warning(
                "Help ticket %s has no customer email, so no receipt was sent.", ticket.id,
            )
            return
        template = ticket.stage_id.template_id
        if not template:
            template = self.env.ref(
                "int_helpdesk_customizations.mail_template_help_received",
                raise_if_not_found=False,
            )
        if not template:
            _logger.warning("No receipt template for help ticket %s.", ticket.id)
            return
        template.sudo().send_mail(ticket.id, force_send=False)

    def _message_get_default_recipients(self):
        recipients = super()._message_get_default_recipients()
        for ticket in self:
            email = (ticket.partner_email or "").strip()
            partner_email = (ticket.partner_id.email or "").strip()
            if email and email.lower() != partner_email.lower():
                recipients[ticket.id] = {
                    "partner_ids": [],
                    "email_to": email,
                    "email_cc": False,
                }
        return recipients

    @api.model
    def _int_help_parse(self, user, company, kind, spec, data, files):
        errors = []
        uploads, upload_error = self._int_help_read_uploads(files, spec)
        if upload_error:
            errors.append(upload_error)
        guest = self._int_help_parse_guest(data, errors) if user._is_public() else None
        if kind == "return":
            parsed = self._int_help_parse_return(user, company, data, errors)
        elif kind == "warranty":
            parsed = self._int_help_parse_warranty(user, company, data, errors)
        elif kind == "feedback":
            parsed = self._int_help_parse_feedback(data, errors)
        elif kind == "general":
            parsed = self._int_help_parse_general(data, errors)
        else:
            parsed = self._int_help_parse_part(data, errors)
        parsed.setdefault("vals", {})
        parsed["guest"] = guest
        if guest:
            parsed["rows"] = guest["rows"] + parsed["rows"]
        if kind in ("return", "warranty") and self._int_help_asks_purchase(user, company):
            rows, vals = self._int_help_parse_purchase(company, data, errors)
            parsed["rows"] = rows + parsed["rows"]
            parsed["vals"].update(vals)
        if errors:
            return None, " ".join(errors)
        parsed["uploads"] = uploads
        if uploads:
            parsed["rows"].append((spec["upload_label"] or "Files", ", ".join(
                item["filename"] for item in uploads
            )))
        return parsed, None

    @api.model
    def _int_help_parse_return(self, user, company, data, errors):
        order = self.env["sale.order"]
        product = self.env["product.product"]
        typed = (data.get("order_id") or "").strip() == TYPED_ORDER
        if typed:
            # Guest checkouts, older orders, or anything else not on their account.
            order_label = (data.get("order_ref") or "").strip()
            product_label = (data.get("product_text") or "").strip()
            if not order_label:
                errors.append(_("Order number is required."))
            if not product_label:
                errors.append(_("Product / SKU is required."))
        else:
            order, order_error = self._int_help_checked_order(user, company, data.get("order_id"), required=True)
            if order_error:
                errors.append(order_error)
            product_id = self._int_help_int(data.get("product_id"))
            if order and not order_error:
                product = self._int_help_order_product(order, product_id)
                if not product:
                    errors.append(_("Choose a product from that order."))
            elif not order_error and not product_id:
                errors.append(_("Choose a product from that order."))
            order_label = order.name if order else ""
            product_label = product.display_name if product else ""
        quantity = self._int_help_number(data.get("quantity"))
        if quantity is None or quantity <= 0:
            errors.append(_("Quantity must be a number greater than zero."))
        reasons = dict(RETURN_REASONS)
        reason = self._int_help_choice(data, "reason", reasons, _("Choose a reason for the return."), errors)
        reason_other = (data.get("reason_other") or "").strip()
        packaging = self._int_help_choice(
            data, "packaging", dict(RETURN_PACKAGING),
            _("Say whether the product is in its original packaging."), errors,
        )
        condition = self._int_help_choice(
            data, "condition", dict(RETURN_CONDITIONS), _("Choose the product condition."), errors,
        )
        outcomes = dict(RETURN_OUTCOMES)
        outcome = (data.get("outcome") or "").strip()
        if outcome and outcome not in outcomes:
            errors.append(_("Choose a desired outcome."))
        outcome_other = (data.get("outcome_other") or "").strip()
        serial = (data.get("serial") or "").strip()
        details = (data.get("details") or "").strip()
        reason_label = reasons.get(reason, "")
        if reason == "other" and reason_other:
            reason_label = f"{reason_label}: {reason_other}"
        outcome_label = outcomes.get(outcome, "")
        if outcome == "other" and outcome_other:
            outcome_label = f"{outcome_label}: {outcome_other}"
        rows = [
            (_("Order (typed, not linked)") if typed else _("Order"), order_label),
            (_("Product"), product_label),
            (_("Serial number"), serial or "\u2014"),
            (_("Quantity"), "" if quantity is None else self._int_help_qty(quantity)),
            (_("Reason for return"), reason_label),
            (_("In original packaging"), dict(RETURN_PACKAGING).get(packaging, "")),
            (_("Product condition"), dict(RETURN_CONDITIONS).get(condition, "")),
            (_("Desired outcome"), outcome_label or "\u2014"),
            (_("Additional information"), details or "\u2014"),
        ]
        return {
            "order": order,
            "product": product,
            "rows": rows,
            "name_left": order_label,
            "name_right": product.name if product else product_label,
        }

    @api.model
    def _int_help_parse_warranty(self, user, company, data, errors):
        order, order_error = self._int_help_checked_order(user, company, data.get("order_id"), required=False)
        if order_error:
            errors.append(order_error)
        product_text = (data.get("product_text") or "").strip()
        if not product_text:
            errors.append(_("Product / SKU is required."))
        product = self.env["product.product"]
        product_id = self._int_help_int(data.get("product_id"))
        if order and product_id:
            product = self._int_help_order_product(order, product_id)
        serial = (data.get("serial") or "").strip()
        if not serial:
            errors.append(_("Serial number is required."))
        install_raw = (data.get("install_date") or "").strip()
        install_date = False
        if not install_raw:
            errors.append(_("Install date is required."))
        else:
            try:
                install_date = fields.Date.to_date(install_raw)
            except (ValueError, TypeError):
                errors.append(_("Install date is not a valid date."))
        failure = (data.get("failure") or "").strip()
        if not failure:
            errors.append(_("Description of failure is required."))
        order_ref = (data.get("order_ref") or "").strip()
        rows = [
            (_("Order"), order.name if order else (order_ref or "\u2014")),
            (_("Product"), product_text),
            (_("Serial number"), serial),
            (_("Install date"), install_date or install_raw),
            (_("Description of failure"), failure),
        ]
        if order:
            name_left, name_right = order.name, product_text
        else:
            name_left, name_right = product_text, failure
        return {
            "order": order,
            "product": product,
            "rows": rows,
            "name_left": name_left,
            "name_right": name_right,
        }

    @api.model
    def _int_help_parse_feedback(self, data, errors):
        area = (data.get("area") or "").strip()
        areas = dict(FEEDBACK_AREAS)
        if area not in areas:
            errors.append(_("Choose an area."))
        description = (data.get("description") or "").strip()
        if not description:
            errors.append(_("Description is required."))
        rows = [
            (_("Area"), areas.get(area, "")),
            (_("Description"), description),
        ]
        return {
            "order": self.env["sale.order"],
            "product": self.env["product.product"],
            "rows": rows,
            "name_left": areas.get(area, ""),
            "name_right": description,
        }

    @api.model
    def _int_help_parse_guest(self, data, errors):
        """Name, email and phone for someone who is not logged in. Same as the public forms."""
        first = (data.get("first_name") or "").strip()
        last = (data.get("last_name") or "").strip()
        email = email_normalize((data.get("email") or "").strip()) or ""
        phone = (data.get("phone") or "").strip()
        company_name = (data.get("company_name") or "").strip()
        if not first:
            errors.append(_("First name is required."))
        if not last:
            errors.append(_("Last name is required."))
        if not email:
            errors.append(_("Enter a valid email address."))
        if not phone:
            errors.append(_("Phone number is required."))
        name = " ".join(part for part in (first, last) if part)
        rows = [
            (_("Name"), name),
            (_("Email"), email),
            (_("Phone"), phone),
        ]
        if company_name:
            rows.append((_("Company"), company_name))
        return {
            "name": self._int_help_clip(name, 120),
            "email": email,
            "phone": phone[:64],
            "company_name": company_name[:120],
            "rows": rows,
        }

    @api.model
    def _int_help_parse_general(self, data, errors):
        subject = (data.get("subject") or "").strip()
        question = (data.get("question") or "").strip()
        if not subject:
            errors.append(_("Subject is required."))
        if not question:
            errors.append(_("Tell us your question."))
        rows = [
            (_("Subject"), subject),
            (_("Question"), question),
        ]
        return {
            "order": self.env["sale.order"],
            "product": self.env["product.product"],
            "rows": rows,
            "name_left": subject,
            "name_right": "",
        }

    @api.model
    def _int_help_parse_part(self, data, errors):
        manufacturer = (data.get("manufacturer") or "").strip()
        part = (data.get("part") or "").strip()
        if not part:
            errors.append(_("Part number or description is required."))
        qty_raw = (data.get("qty_per_year") or "").strip()
        qty = None
        if qty_raw:
            qty = self._int_help_number(qty_raw)
            if qty is None or qty < 0:
                errors.append(_("Estimated quantity per year must be a number that is zero or more."))
        link = (data.get("link") or "").strip()
        if link and not (link.startswith("http://") or link.startswith("https://")):
            errors.append(_("Enter a link that starts with http:// or https://."))
        comments = (data.get("comments") or "").strip()
        rows = [
            (_("Manufacturer"), manufacturer or "\u2014"),
            (_("Part number or description"), part),
            (_("Estimated quantity per year"), self._int_help_qty(qty) if qty is not None else "\u2014"),
            (_("Link"), link or "\u2014"),
            (_("Comments"), comments or "\u2014"),
        ]
        return {
            "order": self.env["sale.order"],
            "product": self.env["product.product"],
            "rows": rows,
            "name_left": manufacturer or part,
            "name_right": part if manufacturer else "",
        }

    @api.model
    def _int_help_checked_order(self, user, company, raw, required):
        raw = (raw or "").strip()
        if not raw:
            if required:
                return self.env["sale.order"], _("Choose an order.")
            return self.env["sale.order"], None
        order_id = self._int_help_int(raw)
        order = self._int_help_own_order(user, company, order_id)
        if not order:
            return self.env["sale.order"], _("That order cannot be used.")
        return order, None

    @api.model
    def _int_help_choice(self, data, key, choices, message, errors):
        value = (data.get(key) or "").strip()
        if value not in choices:
            errors.append(message)
            return ""
        return value

    @api.model
    def _int_help_asks_purchase(self, user, company):
        """Retail users are asked where they bought it. Dealers and staff are not."""
        if user.has_group("base.group_user"):
            return False
        return not user._int_help_is_approved_dealer(company)

    @api.model
    def _int_help_parse_purchase(self, company, data, errors):
        sources = dict(PURCHASE_SOURCES)
        source = self._int_help_choice(
            data, "purchase_source", sources, _("Tell us where you bought it."), errors,
        )
        dealer = self.env["res.partner"]
        if source == "dealer":
            dealer_id = self._int_help_int(data.get("purchase_dealer_id"))
            dealers = self.env["res.partner"]._int_help_dealer_companies(company)
            dealer = dealers.filtered(lambda partner: partner.id == dealer_id)
            if not dealer:
                errors.append(_("Choose the dealer you bought it from."))
        label = sources.get(source, "")
        if dealer:
            label = f"{label}: {dealer.name}"
        vals = {
            "int_help_purchase_source": source or False,
            "int_help_purchase_dealer_id": dealer.id or False,
        }
        return [(_("Where did you buy it?"), label)], vals

    @api.model
    def _int_help_read_uploads(self, files, spec):
        named = []
        for upload in files:
            filename = (getattr(upload, "filename", None) or "").strip()
            if filename:
                named.append(upload)
        if spec["max_files"] <= 0:
            if named:
                return [], _("This form does not accept files.")
            return [], None
        if len(named) > spec["max_files"]:
            return [], _("Attach up to %s files.") % spec["max_files"]
        allowed = dict(IMAGE_TYPES)
        if spec["allow_video"]:
            allowed.update(VIDEO_TYPES)
        stored = []
        for upload in named:
            filename = os.path.basename((upload.filename or "").replace("\\", "/")).strip()
            mimetype = (
                getattr(upload, "mimetype", None) or getattr(upload, "content_type", None) or ""
            )
            mimetype = mimetype.split(";", 1)[0].strip().lower()
            ext = os.path.splitext(filename)[1].lower().lstrip(".")
            if ext not in allowed or mimetype not in allowed.get(ext, ()):
                return [], _("That file type is not allowed.")
            content = upload.read()
            if isinstance(content, str):
                content = content.encode()
            if not content:
                return [], _("That file is empty.")
            if len(content) > MAX_UPLOAD_BYTES:
                return [], _("Each file must be 20 MB or smaller.")
            stored.append({
                "filename": filename,
                "mimetype": mimetype,
                "content": content,
            })
        return stored, None

    @api.model
    def _int_help_ticket_vals(self, user, company, spec, team, tag, parsed):
        description = self._int_help_description(parsed["rows"])
        guest = parsed.get("guest")
        vals = {
            "name": self._int_help_ticket_name(spec["name"], parsed["name_left"], parsed["name_right"]),
            "team_id": team.id,
            "tag_ids": [Command.set([tag.id])],
            "description": description,
        }
        if guest:
            # Not the Public user's contact. Helpdesk links or creates the customer from the email.
            if "partner_name" in self._fields:
                vals["partner_name"] = guest["name"] or False
            if "partner_email" in self._fields:
                vals["partner_email"] = guest["email"] or False
            if "partner_phone" in self._fields:
                vals["partner_phone"] = guest["phone"] or False
            if "partner_company_name" in self._fields and guest["company_name"]:
                vals["partner_company_name"] = guest["company_name"]
        else:
            vals["partner_id"] = user.partner_id.id
        if "company_id" in self._fields:
            vals["company_id"] = company.id
        if not guest and "partner_name" in self._fields:
            vals["partner_name"] = (user.partner_id.name or user.name or "").strip() or False
        if not guest and "partner_email" in self._fields:
            vals["partner_email"] = (user.email or user.partner_id.email or "").strip() or False
        if "sale_order_id" in self._fields and parsed["order"]:
            vals["sale_order_id"] = parsed["order"].id
        if "product_id" in self._fields and parsed["product"]:
            vals["product_id"] = parsed["product"].id
        vals.update(parsed.get("vals") or {})
        return vals

    @api.model
    def _int_help_ticket_name(self, kind_label, left, right):
        left = self._int_help_clip(left, 60)
        right = self._int_help_clip(right, 80)
        if left and right:
            name = f"[{kind_label}] {left} {EN_DASH} {right}"
        elif left or right:
            name = f"[{kind_label}] {left or right}"
        else:
            name = f"[{kind_label}]"
        return name[:200]

    @api.model
    def _int_help_description(self, rows):
        items = [
            Markup("<li><strong>%s:</strong> %s</li>") % (escape(label), escape(value))
            for label, value in rows
        ]
        html = Markup("<ul>%s</ul>") % Markup("").join(items)
        field = self._fields.get("description")
        if field and field.type != "html":
            return "\n".join(f"{label}: {value}" for label, value in rows)
        return html

    @api.model
    def _int_help_store_attachments(self, ticket, uploads):
        if not uploads:
            return self.env["ir.attachment"]
        Attachment = self.env["ir.attachment"].sudo()
        created = Attachment
        for item in uploads:
            created |= Attachment.create({
                "name": item["filename"],
                "datas": base64.b64encode(item["content"]).decode(),
                "res_model": "helpdesk.ticket",
                "res_id": ticket.id,
                "type": "binary",
                "mimetype": item["mimetype"],
                "public": False,
            })
        return created

    @api.model
    def _int_help_note_on_order(self, order, ticket, user):
        ref = escape(self._int_help_reference(ticket))
        url = escape(f"/web#id={ticket.id}&model=helpdesk.ticket&view_type=form")
        body = Markup(
            "<p>Help &amp; Feedback ticket <a href=\"%s\">%s</a> was opened from the dealer portal.</p>"
        ) % (url, ref)
        try:
            order.sudo().message_post(
                body=body,
                subtype_xmlid="mail.mt_note",
                author_id=user.partner_id.id,
            )
        except Exception:
            _logger.exception(
                "Could not note Help & Feedback ticket %s on %s.", ticket.id, order.display_name,
            )

    @api.model
    def _int_help_clip(self, text, limit):
        text = " ".join((text or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "\u2026"

    @api.model
    def _int_help_int(self, value):
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return 0
        return number if number > 0 else 0

    @api.model
    def _int_help_number(self, value):
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return number

    @api.model
    def _int_help_qty(self, number):
        if number is None:
            return ""
        if float(number).is_integer():
            return str(int(number))
        return str(number)
