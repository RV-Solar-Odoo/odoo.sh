import base64
import logging
import math
import os
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.fields import Command

_logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
NO_ORDERS_MESSAGE = "No orders found \u2014 use Feedback instead."
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

RETURN_REASONS = (
    ("wrong_item", "wrong item"),
    ("damaged", "damaged in shipping"),
    ("ordered_error", "ordered in error"),
    ("other", "other"),
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
        "code": "help_return",
        "max_files": 5,
        "allow_video": False,
        "upload_label": "Photos",
        "accept": "image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp",
    },
    "warranty": {
        "title": "Start a warranty claim",
        "name": "Warranty Claim",
        "tag_field": "int_help_tag_warranty_id",
        "code": "help_warranty",
        "max_files": 5,
        "allow_video": True,
        "upload_label": "Photos or video",
        "accept": "image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,.jpg,.jpeg,.png,.gif,.webp,.mp4,.mov",
    },
    "feedback": {
        "title": "Website & operations feedback",
        "name": "Feedback",
        "tag_field": "int_help_tag_feedback_id",
        "code": "help_feedback",
        "max_files": 3,
        "allow_video": False,
        "upload_label": "Screenshot",
        "accept": "image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp",
    },
    "part": {
        "title": "Request a part we don't stock",
        "name": "Part Request",
        "tag_field": "int_help_tag_part_id",
        "code": "help_part",
        "max_files": 0,
        "allow_video": False,
        "upload_label": "",
        "accept": "",
    },
}


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    @api.model
    def _int_help_kind(self, kind):
        return HELP_KINDS.get(kind)

    @api.model
    def _int_help_prepare(self, user, company, kind):
        """Values the form needs. A return with no orders explains that, instead of a broken form."""
        spec = HELP_KINDS[kind]
        orders = self._int_help_orders(user, company)
        return {
            "kind": kind,
            "title": spec["title"],
            "orders": orders,
            "notice": NO_ORDERS_MESSAGE if kind == "return" and not orders else False,
            "reasons": RETURN_REASONS,
            "areas": FEEDBACK_AREAS,
            "max_files": spec["max_files"],
            "accept": spec["accept"],
            "upload_label": spec["upload_label"],
        }

    @api.model
    def _int_help_submit(self, user, company, kind, data, files=None):
        """Validate a portal submission and create the ticket.

        Returns ``{"ticket": record}`` or ``{"error": message}``. The customer
        confirmation email is the team's New stage template, not a second mail
        from here.
        """
        spec = self._int_help_kind(kind)
        if not spec:
            return {"error": _("That request type is not available.")}
        access_error = self._int_help_access_error(user, company)
        if access_error:
            return {"error": access_error}
        if kind == "return" and not self._int_help_orders(user, company):
            return {"error": NO_ORDERS_MESSAGE, "notice": NO_ORDERS_MESSAGE}
        tag = company.sudo()[spec["tag_field"]]
        if not tag:
            _logger.warning(
                "Help & Feedback tag %s is not configured for %s.",
                spec["tag_field"], company.display_name,
            )
            return {"error": _("This request type is not set up yet.")}
        parsed, error = self._int_help_parse(user, company, kind, spec, data or {}, files or [])
        if error:
            return {"error": error}
        if self._int_help_rate_limited(user, company):
            return {"error": _("You can submit up to 10 Help & Feedback requests per hour.")}
        team = company._int_help_team_or_warn()
        vals = self._int_help_ticket_vals(user, company, spec, team, tag, parsed)
        ticket = self.sudo().with_company(company).create(vals)
        self._int_help_store_attachments(ticket, parsed["uploads"])
        if parsed["order"] and kind in ("return", "warranty"):
            self._int_help_note_on_order(parsed["order"], ticket, user)
        self.env["int.helpdesk.alert.list"]._int_notify(
            spec["code"], ticket, ticket.name, company,
        )
        return {"ticket": ticket}

    @api.model
    def _int_help_access_error(self, user, company):
        if not user or user._is_public():
            return _("Help & Feedback is not available for this account.")
        if not company._int_help_team_or_warn():
            return _("Help & Feedback is not available right now.")
        if user.has_group("base.group_user"):
            return None
        if user.has_group("base.group_portal") and user._int_help_is_approved_dealer(company):
            return None
        return _("Help & Feedback is not available for this account.")

    @api.model
    def _int_help_order_domain(self, user, company):
        commercial = user.partner_id.sudo().commercial_partner_id
        if not commercial:
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
        seen = set()
        options = []
        for line in order.order_line:
            product = line.product_id
            if line.display_type or not product or product.id in seen:
                continue
            seen.add(product.id)
            sku = product.default_code
            label = f"{sku} {EN_DASH} {product.name}" if sku else product.name
            options.append({"product_id": product.id, "name": label})
        return options

    @api.model
    def _int_help_order_product(self, order, product_id):
        if not order or not product_id:
            return self.env["product.product"]
        lines = order.order_line.filtered(
            lambda line: not line.display_type and line.product_id.id == product_id
        )
        return lines[:1].product_id

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
    def _int_help_parse(self, user, company, kind, spec, data, files):
        errors = []
        uploads, upload_error = self._int_help_read_uploads(files, spec)
        if upload_error:
            errors.append(upload_error)
        if kind == "return":
            parsed = self._int_help_parse_return(user, company, data, errors)
        elif kind == "warranty":
            parsed = self._int_help_parse_warranty(user, company, data, errors)
        elif kind == "feedback":
            parsed = self._int_help_parse_feedback(data, errors)
        else:
            parsed = self._int_help_parse_part(data, errors)
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
        order, order_error = self._int_help_checked_order(user, company, data.get("order_id"), required=True)
        if order_error:
            errors.append(order_error)
        product = self.env["product.product"]
        product_id = self._int_help_int(data.get("product_id"))
        if order and not order_error:
            product = self._int_help_order_product(order, product_id)
            if not product:
                errors.append(_("Choose a product from that order."))
        elif not order_error and not product_id:
            errors.append(_("Choose a product from that order."))
        quantity = self._int_help_number(data.get("quantity"))
        if quantity is None or quantity <= 0:
            errors.append(_("Quantity must be a number greater than zero."))
        reason = (data.get("reason") or "").strip()
        reasons = dict(RETURN_REASONS)
        if reason not in reasons:
            errors.append(_("Choose a reason."))
        serial = (data.get("serial") or "").strip()
        details = (data.get("details") or "").strip()
        rows = [
            (_("Order"), order.name if order else ""),
            (_("Product"), product.display_name if product else ""),
            (_("Serial number"), serial or "\u2014"),
            (_("Quantity"), "" if quantity is None else self._int_help_qty(quantity)),
            (_("Reason"), reasons.get(reason, "")),
            (_("Details"), details or "\u2014"),
        ]
        return {
            "order": order,
            "product": product,
            "rows": rows,
            "name_left": order.name if order else "",
            "name_right": product.name if product else "",
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
        rows = [
            (_("Order"), order.name if order else "\u2014"),
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
    def _int_help_parse_part(self, data, errors):
        manufacturer = (data.get("manufacturer") or "").strip()
        if not manufacturer:
            errors.append(_("Manufacturer is required."))
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
        rows = [
            (_("Manufacturer"), manufacturer),
            (_("Part number or description"), part),
            (_("Estimated quantity per year"), self._int_help_qty(qty) if qty is not None else "\u2014"),
            (_("Link"), link or "\u2014"),
        ]
        return {
            "order": self.env["sale.order"],
            "product": self.env["product.product"],
            "rows": rows,
            "name_left": manufacturer,
            "name_right": part,
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
        vals = {
            "name": self._int_help_ticket_name(spec["name"], parsed["name_left"], parsed["name_right"]),
            "team_id": team.id,
            "partner_id": user.partner_id.id,
            "tag_ids": [Command.set([tag.id])],
            "description": description,
        }
        if "company_id" in self._fields:
            vals["company_id"] = company.id
        if "partner_email" in self._fields:
            vals["partner_email"] = user.email or user.partner_id.email or False
        if "sale_order_id" in self._fields and parsed["order"]:
            vals["sale_order_id"] = parsed["order"].id
        if "product_id" in self._fields and parsed["product"]:
            vals["product_id"] = parsed["product"].id
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
