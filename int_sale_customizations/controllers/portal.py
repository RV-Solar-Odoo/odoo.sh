import base64
from datetime import date
from urllib.parse import quote

from odoo import _
from odoo.exceptions import UserError
from odoo.http import request, route

from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.sale.controllers.portal import CustomerPortal


class CustomerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "int_backorder_count" in counters:
            commercial = request.env.user.partner_id.commercial_partner_id
            moves = request.env["stock.picking"]._int_portal_backorder_moves(commercial)
            values["int_backorder_count"] = len(moves)
        return values

    def _get_sale_searchbar_sortings(self):
        sortings = super()._get_sale_searchbar_sortings()
        sortings.update({
            "date_asc": {"label": _("Oldest"), "order": "date_order asc, id asc"},
            "name": {"label": _("Order #"), "order": "name desc"},
            "amount": {"label": _("Total"), "order": "amount_total desc, id desc"},
        })
        sortings["date"]["label"] = _("Newest")
        return sortings

    def _prepare_sale_portal_rendering_values(
        self, page=1, date_begin=None, date_end=None, sortby=None, quotation_page=False, **kwargs
    ):
        if quotation_page:
            return super()._prepare_sale_portal_rendering_values(
                page=page, date_begin=date_begin, date_end=date_end, sortby=sortby,
                quotation_page=True, **kwargs,
            )
        user = request.env.user
        if user.share and not user.int_portal_can("view_orders"):
            return request.redirect("/my")
        search = (kwargs.get("search") or "").strip()
        search_in = kwargs.get("search_in") or "all"
        filterby = kwargs.get("filterby") or "all"
        sortby = sortby or "date"
        sortings = self._get_sale_searchbar_sortings()
        if sortby not in sortings:
            sortby = "date"
        commercial = user.partner_id.commercial_partner_id
        SaleOrder = request.env["sale.order"]
        domain = SaleOrder._int_portal_order_domain(
            commercial, search=search, search_in=search_in, filterby=filterby,
            date_begin=date_begin, date_end=date_end,
        )
        url_args = {
            "date_begin": date_begin,
            "date_end": date_end,
            "sortby": sortby,
            "filterby": filterby,
            "search": search,
            "search_in": search_in,
        }
        total = SaleOrder.search_count(domain) if SaleOrder.has_access("read") else 0
        pager_values = portal_pager(
            url="/my/orders",
            total=total,
            page=page,
            step=self._items_per_page,
            url_args=url_args,
        )
        orders = SaleOrder._int_portal_orders_page(
            domain,
            sortings[sortby]["order"],
            user.int_pinned_order_ids.ids,
            self._items_per_page,
            pager_values["offset"],
        )
        values = self._prepare_portal_layout_values()
        values.update({
            "date": date_begin,
            "date_begin": date_begin or "",
            "date_end": date_end or "",
            "orders": orders.sudo(),
            "page_name": "order",
            "pager": pager_values,
            "default_url": "/my/orders",
            "sortby": sortby,
            "search": search,
            "search_in": search_in,
            "filterby": filterby,
            "int_search_error": kwargs.get("int_error") or "",
        })
        return values

    def _int_owned_order(self, order_id):
        order = request.env["sale.order"].browse(order_id).exists()
        user = request.env.user
        if not order or not order._int_owned_by(user) or not user.int_portal_can("view_orders"):
            return request.env["sale.order"]
        return order

    def _int_cart(self):
        website = request.website
        cart = website._get_and_cache_current_cart()
        if not cart:
            cart = website._create_cart()
        return cart

    def _int_add_order_lines(self, lines):
        cart = self._int_cart()
        for line in lines:
            cart._cart_add(product_id=line.product_id.id, quantity=line.product_uom_qty)
        return cart

    @route(["/my/orders", "/my/orders/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_orders(self, **kwargs):
        values = self._prepare_sale_portal_rendering_values(quotation_page=False, **kwargs)
        if not isinstance(values, dict):
            return values
        request.session["my_orders_history"] = values["orders"].ids[:100]
        return request.render("sale.portal_my_orders", values)

    @route("/my/orders/export", type="http", auth="user", website=True)
    def int_orders_export(self, export_format="xlsx", **kwargs):
        user = request.env.user
        if not user.int_portal_can("export_orders"):
            return request.redirect("/my/orders")
        commercial = user.partner_id.commercial_partner_id
        domain = request.env["sale.order"]._int_portal_order_domain(
            commercial,
            search=kwargs.get("search"),
            search_in=kwargs.get("search_in") or "all",
            filterby=kwargs.get("filterby") or "all",
            date_begin=kwargs.get("date_begin"),
            date_end=kwargs.get("date_end"),
        )
        orders = request.env["sale.order"].search(domain, limit=10001)
        rows = orders.sudo()._int_export_rows()
        if len(rows) > 10000:
            return request.redirect("/my/orders?int_error=%s" % quote(_("Export is limited to 10,000 rows. Narrow the filters.")))
        stamp = date.today().isoformat()
        if export_format == "csv":
            content = orders.sudo()._int_export_csv()
            filename = f"orders_{stamp}.csv"
            mimetype = "text/csv"
        else:
            content = orders.sudo()._int_export_xlsx()
            filename = f"orders_{stamp}.xlsx"
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return request.make_response(content, headers=[
            ("Content-Type", mimetype),
            ("Content-Disposition", f"attachment; filename={filename}"),
        ])

    @route("/my/backorders", type="http", auth="user", website=True)
    def int_portal_backorders(self, **kwargs):
        user = request.env.user
        if not user.int_portal_can("view_orders"):
            return request.redirect("/my")
        moves = request.env["stock.picking"]._int_portal_backorder_moves(user.partner_id.commercial_partner_id)
        return request.render("int_sale_customizations.portal_backorders", {
            "page_name": "int_backorders",
            "int_backorder_moves": moves.sudo(),
        })

    @route("/my/orders/<int:order_id>/pin", type="http", auth="user", website=True, methods=["POST"])
    def int_order_pin(self, order_id, **kwargs):
        order = self._int_owned_order(order_id)
        if not order:
            return request.redirect("/my/orders")
        try:
            request.env.user.int_portal_toggle_pin(order)
        except UserError as exc:
            return request.redirect("/my/orders?int_error=%s" % quote(str(exc.args[0])))
        return request.redirect(kwargs.get("redirect") or "/my/orders")

    @route("/my/orders/<int:order_id>/reorder", type="http", auth="user", website=True, methods=["POST"])
    def int_order_reorder(self, order_id, confirm=None, **kwargs):
        user = request.env.user
        order = self._int_owned_order(order_id)
        if not order or not user.int_portal_can("place_orders"):
            return request.redirect("/my/orders")
        addable, skipped = order.sudo()._int_reorder_plan(request.website)
        if skipped and not confirm:
            return request.render("int_sale_customizations.portal_reorder_review", {
                "sale_order": order.sudo(),
                "int_addable": addable,
                "int_skipped": skipped,
            })
        if addable:
            self._int_add_order_lines(addable)
        return request.redirect("/shop/cart")

    @route("/my/orders/<int:order_id>/cancel", type="http", auth="user", website=True, methods=["POST"])
    def int_order_cancel_request(self, order_id, reason="", note="", preference="", **kwargs):
        order = self._int_owned_order(order_id)
        if not order:
            return request.redirect("/my/orders")
        try:
            order.int_portal_request_cancel(request.env.user, reason, note, preference)
        except UserError as exc:
            url = order.get_portal_url()
            separator = "&" if "?" in url else "?"
            return request.redirect(f"{url}{separator}int_error={quote(str(exc.args[0]))}")
        return request.redirect(order.get_portal_url())

    @route("/my/po-template.xlsx", type="http", auth="user", website=True)
    def int_po_template(self, **kwargs):
        if not request.env.user.int_portal_can("upload_po"):
            return request.redirect("/my")
        content = request.env["sale.order"]._int_po_template_xlsx()
        return request.make_response(content, headers=[
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", "attachment; filename=po_template.xlsx"),
        ])

    @route("/my/po-upload", type="http", auth="user", website=True)
    def int_po_upload_page(self, **kwargs):
        if not request.env.user.int_portal_can("upload_po"):
            return request.redirect("/my")
        return request.render("int_sale_customizations.portal_po_upload", {
            "page_name": "int_po",
            "int_error": kwargs.get("error") or "",
            "int_po_done": kwargs.get("done") or "",
        })

    @route("/my/po-upload/submit", type="http", auth="user", website=True, methods=["POST"])
    def int_po_upload_submit(self, po_file=None, po_number="", **kwargs):
        user = request.env.user
        if not user.int_portal_can("upload_po"):
            return request.redirect("/my")
        upload = po_file or request.httprequest.files.get("po_file")
        if not upload:
            return request.redirect("/my/po-upload?error=%s" % quote(_("Choose a file.")))
        raw = upload.read()
        if len(raw) > 10 * 1024 * 1024:
            return request.redirect("/my/po-upload?error=%s" % quote(_("The file must be 10 MB or smaller.")))
        name = (upload.filename or "").lower()
        if name.endswith(".pdf"):
            return self._int_po_pdf(user, raw, upload.filename, po_number)
        try:
            po_from_file, parsed = request.env["sale.order"]._int_po_rows_from_xlsx(raw)
        except UserError as exc:
            return request.redirect("/my/po-upload?error=%s" % quote(str(exc.args[0])))
        po_number = (po_number or po_from_file or "").strip()
        added, rejected = request.env["sale.order"]._int_match_po_rows(parsed, request.website)
        cart = self._int_cart()
        for product, quantity in added:
            cart._cart_add(product_id=product.id, quantity=quantity)
        if po_number:
            cart.sudo().write({"client_order_ref": po_number})
        return request.render("int_sale_customizations.portal_po_result", {
            "page_name": "int_po",
            "int_added": added,
            "int_rejected": rejected,
            "int_po_number": po_number,
        })

    def _int_po_pdf(self, user, raw, filename, po_number):
        website = request.website
        order = request.env["sale.order"].sudo().create({
            "partner_id": user.partner_id.id,
            "company_id": website.company_id.id,
            "website_id": website.id,
            "client_order_ref": (po_number or "").strip() or False,
        })
        attachment = request.env["ir.attachment"].sudo().create({
            "name": filename or "purchase-order.pdf",
            "datas": base64.b64encode(raw),
            "res_model": "sale.order",
            "res_id": order.id,
            "type": "binary",
            "public": False,
        })
        order.message_post(
            body=_("Purchase order uploaded from My Portal."),
            attachment_ids=[attachment.id],
        )
        salesperson = user.partner_id.commercial_partner_id.user_id
        if salesperson and not salesperson.share:
            order.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Enter PO from upload"),
                user_id=salesperson.id,
            )
        else:
            order.message_post(body=_("No salesperson is set. Enter PO from upload."))
        return request.redirect("/my/po-upload?done=1")
