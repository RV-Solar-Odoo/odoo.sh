import base64
import os
import re
from datetime import date
from urllib.parse import quote

from odoo import _
from odoo.exceptions import UserError
from odoo.http import request, route
from odoo.tools.misc import formatLang

from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.sale.controllers.portal import CustomerPortal


class CustomerPortal(CustomerPortal):

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
            values = super()._prepare_sale_portal_rendering_values(
                page=page, date_begin=date_begin, date_end=date_end, sortby=sortby,
                quotation_page=True, **kwargs,
            )
            values.update(self._int_order_tab_values("quotes"))
            return values
        user = request.env.user
        if user.share and not user.int_portal_can("view_orders"):
            return request.redirect("/my")
        tab = "backorders" if kwargs.get("int_tab") == "backorders" else "all"
        search = (kwargs.get("search") or "").strip() if tab == "all" else ""
        search_in = kwargs.get("search_in") or "all"
        filterby = "backordered" if tab == "backorders" else (kwargs.get("filterby") or "all")
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
        url = "/my/backorders" if tab == "backorders" else "/my/orders"
        url_args = {"sortby": sortby}
        if tab == "all":
            url_args.update({
                "date_begin": date_begin,
                "date_end": date_end,
                "filterby": filterby,
                "search": search,
                "search_in": search_in,
            })
        can_read = SaleOrder.has_access("read")
        total = SaleOrder.search_count(domain) if can_read else 0
        pager_values = portal_pager(
            url=url,
            total=total,
            page=page,
            step=self._items_per_page,
            url_args=url_args,
        )
        orders = SaleOrder.search(
            domain,
            order=sortings[sortby]["order"],
            limit=self._items_per_page,
            offset=pager_values["offset"],
        ) if can_read else SaleOrder
        values = self._prepare_portal_layout_values()
        values.update({
            "date": date_begin,
            "date_begin": date_begin or "",
            "date_end": date_end or "",
            "orders": orders.sudo(),
            "page_name": "order",
            "pager": pager_values,
            "default_url": url,
            "sortby": sortby,
            "search": search,
            "search_in": search_in,
            "filterby": filterby,
            "int_search_error": kwargs.get("int_error") or "",
            "int_backordered_ids": set(SaleOrder._int_portal_backordered_ids(commercial)),
            "int_fav_by_order": self._int_favorites_by_order(orders),
        })
        values.update(self._int_order_tab_values(tab))
        return values

    # My Orders tabs: All Orders, Favorite Orders, Backorders, Quotes.

    def _int_company(self):
        return request.website.company_id or request.env.company

    def _int_order_tab_values(self, tab):
        user = request.env.user
        commercial = user.partner_id.commercial_partner_id
        SaleOrder = request.env["sale.order"]
        can_read = SaleOrder.has_access("read")
        counts = {"all": 0, "favorites": 0, "backorders": 0, "quotes": 0}
        if can_read:
            counts["all"] = SaleOrder.search_count(SaleOrder._int_portal_order_domain(commercial))
            counts["backorders"] = SaleOrder.search_count(
                SaleOrder._int_portal_order_domain(commercial, filterby="backordered")
            )
            counts["quotes"] = SaleOrder.search_count(self._prepare_quotations_domain(user.partner_id))
        counts["favorites"] = len(request.env["int.favorite.order"]._int_for_user(user, self._int_company()))
        return {
            "int_tab": tab,
            "int_tab_counts": counts,
            "int_can_edit_favorites": user.int_portal_can("pin_orders"),
            "int_can_order": user.int_portal_can("place_orders") and not user.int_portal_ordering_blocked(),
            "int_fav_notice": self._int_favorite_notice(),
        }

    def _int_favorites_by_order(self, orders):
        user = request.env.user
        if user._is_public():
            return {}
        return request.env["int.favorite.order"]._int_by_order(user, self._int_company(), orders)

    def _int_favorite_notice(self):
        return request.env["int.favorite.order"]._int_notice(
            request.env.user, self._int_company(), request.params,
        )

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

    @route(["/my/deliveries", "/my/deliveries/page/<int:page>"], type="http", auth="user", website=True)
    def int_portal_deliveries(self, **kwargs):
        """The Deliveries list is gone. Backorders have their own tab on My Orders."""
        return request.redirect("/my/backorders")

    @route(["/my/backorders", "/my/backorders/page/<int:page>"], type="http", auth="user", website=True)
    def int_portal_backorders(self, **kwargs):
        kwargs["int_tab"] = "backorders"
        values = self._prepare_sale_portal_rendering_values(quotation_page=False, **kwargs)
        if not isinstance(values, dict):
            return values
        return request.render("sale.portal_my_orders", values)

    @route("/my/deliveries/<int:picking_id>", type="http", auth="user", website=True)
    def int_portal_delivery(self, picking_id, **kwargs):
        user = request.env.user
        if not user.int_portal_can("view_orders"):
            return request.redirect("/my")
        delivery = request.env["stock.picking"]._int_portal_owned_delivery(user, picking_id)
        if not delivery:
            return request.redirect("/my/orders")
        if delivery.sale_id:
            delivery.sale_id.sudo()._portal_ensure_token()
        return request.render("int_sale_customizations.portal_delivery", {
            "page_name": "int_delivery",
            "delivery": delivery,
        })

    # Favorite orders: saved product lists, shared by the dealer's logins.

    @staticmethod
    def _int_back(url, default):
        """Only send people back to a My Portal page or the cart."""
        url = url or ""
        if url.startswith(("/my/", "/shop/cart")) and not url.startswith("//") and "\\" not in url:
            return url
        return default

    @staticmethod
    def _int_with_param(url, key, value):
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{key}={quote(str(value))}"

    def _int_favorite(self, favorite_id, active=True):
        return request.env["int.favorite.order"]._int_for_user(
            request.env.user, self._int_company(), favorite_id, active=active,
        )

    def _int_live_prices(self, products):
        """{product id: price} as the shop shows it to this customer today."""
        prices = {}
        for product in products:
            if product.id not in prices:
                prices[product.id] = product._get_combination_info_variant()["price"]
        return prices

    def _int_error_redirect(self, url, exc):
        return request.redirect(self._int_with_param(url, "int_error", exc.args[0]))

    @route("/my/favorites", type="http", auth="user", website=True)
    def int_portal_favorites(self, **kwargs):
        user = request.env.user
        if user.share and not user.int_portal_can("view_orders"):
            return request.redirect("/my")
        favorites = request.env["int.favorite.order"]._int_for_user(user, self._int_company())
        prices = self._int_live_prices(favorites.line_ids.product_id)
        totals = {
            favorite.id: sum(prices[line.product_id.id] * line.quantity for line in favorite.line_ids)
            for favorite in favorites
        }
        values = self._prepare_portal_layout_values()
        values.update(self._int_order_tab_values("favorites"))
        values.update({
            "page_name": "order",
            "favorites": favorites,
            "int_prices": prices,
            "int_totals": totals,
            "int_open_id": int(kwargs["open"]) if str(kwargs.get("open", "")).isdigit() else False,
            "int_error": kwargs.get("int_error") or "",
            "int_owned_orders": favorites.source_order_id.filtered(lambda order: order._int_owned_by(user)),
        })
        return request.render("int_sale_customizations.portal_my_favorites", values)

    @route("/my/favorites/<int:favorite_id>/edit", type="http", auth="user", website=True)
    def int_portal_favorite_edit(self, favorite_id, **kwargs):
        user = request.env.user
        favorite = self._int_favorite(favorite_id)
        if not favorite or not user.int_portal_can("pin_orders"):
            return request.redirect("/my/favorites")
        values = self._prepare_portal_layout_values()
        values.update(self._int_order_tab_values("favorites"))
        values.update({
            "page_name": "int_favorite",
            "favorite": favorite,
            "int_prices": self._int_live_prices(favorite.line_ids.product_id),
            "int_error": kwargs.get("int_error") or "",
        })
        return request.render("int_sale_customizations.portal_favorite_edit", values)

    @route("/my/favorites/<int:favorite_id>/save", type="http", auth="user", website=True, methods=["POST"])
    def int_portal_favorite_save(self, favorite_id, name=None, **post):
        favorite = self._int_favorite(favorite_id)
        if not favorite:
            return request.redirect("/my/favorites")
        quantities, removed, added = {}, set(), {}
        for key, value in post.items():
            if key.startswith("qty_") and key[4:].isdigit():
                quantities[int(key[4:])] = value
            elif key.startswith("remove_") and key[7:].isdigit() and value == "1":
                removed.add(int(key[7:]))
            elif key.startswith("add_") and key[4:].isdigit():
                added[int(key[4:])] = value
        try:
            favorite._int_apply_edit(
                request.env.user, name=name, quantities=quantities, removed=removed,
                added=added, website=request.website,
            )
        except UserError as exc:
            return self._int_error_redirect(f"/my/favorites/{favorite.id}/edit", exc)
        return request.redirect(f"/my/favorites?open={favorite.id}&int_fav_saved={favorite.id}")

    @route("/my/favorites/<int:favorite_id>/delete", type="http", auth="user", website=True, methods=["POST"])
    def int_portal_favorite_delete(self, favorite_id, redirect=None, **kwargs):
        back = self._int_back(redirect, "/my/favorites")
        favorite = self._int_favorite(favorite_id)
        if not favorite:
            return request.redirect(back)
        try:
            favorite._int_archive(request.env.user)
        except UserError as exc:
            return self._int_error_redirect(back, exc)
        return request.redirect(self._int_with_param(back, "int_fav_removed", favorite.id))

    @route("/my/favorites/<int:favorite_id>/restore", type="http", auth="user", website=True, methods=["POST"])
    def int_portal_favorite_restore(self, favorite_id, redirect=None, **kwargs):
        back = self._int_back(redirect, "/my/favorites")
        favorite = self._int_favorite(favorite_id, active=False)
        if not favorite:
            return request.redirect(back)
        try:
            favorite._int_restore(request.env.user, self._int_company())
        except UserError as exc:
            return self._int_error_redirect(back, exc)
        return request.redirect(back)

    @route("/my/favorites/<int:favorite_id>/cart", type="http", auth="user", website=True, methods=["POST"])
    def int_portal_favorite_cart(self, favorite_id, confirm=None, **post):
        user = request.env.user
        favorite = self._int_favorite(favorite_id)
        if not favorite or not user.int_portal_can("place_orders") or user.int_portal_ordering_blocked():
            return request.redirect("/my/favorites")
        selected = None
        if post.get("selected") == "1":
            selected = {}
            for key, value in post.items():
                if key.startswith("line_") and key[5:].isdigit():
                    line_id = int(key[5:])
                    selected[line_id] = post.get(f"qty_{line_id}", value)
        addable, skipped = favorite._int_cart_plan(request.website, selected)
        if skipped and not confirm:
            return request.render("int_sale_customizations.portal_favorite_review", {
                "page_name": "int_favorite",
                "favorite": favorite,
                "int_addable": addable,
                "int_skipped": skipped,
                "int_selected": selected,
            })
        if not addable:
            return request.redirect(self._int_with_param(
                "/my/favorites", "int_error", _("None of the selected products can be ordered online."),
            ))
        cart = self._int_cart()
        for product, qty in addable:
            cart._cart_add(product_id=product.id, quantity=qty)
        return request.redirect("/shop/cart")

    @route("/my/favorites/products", type="http", auth="user", website=True, methods=["GET"])
    def int_portal_favorite_products(self, q="", **kwargs):
        """Products to add to a favorite: name or SKU, on this website, at today's price."""
        if not request.env.user.int_portal_can("pin_orders"):
            return request.make_json_response({"products": []}, status=403)
        term = " ".join((q or "").split())[:60]
        if len(term) < 2:
            return request.make_json_response({"products": []})
        company = self._int_company()
        candidates = request.env["product.product"].sudo().search([
            ("sale_ok", "=", True),
            ("company_id", "in", [company.id, False]),
            "|", ("name", "ilike", term), ("default_code", "ilike", term),
        ], limit=30)
        SaleOrder = request.env["sale.order"]
        products = candidates.filtered(
            lambda product: SaleOrder._int_product_on_website(product, request.website)
        )[:8]
        prices = self._int_live_prices(products)
        currency = request.website.currency_id
        return request.make_json_response({"products": [{
            "id": product.id,
            "name": product.with_context(display_default_code=False).display_name,
            "sku": product.default_code or "",
            "price": prices[product.id],
            "price_label": formatLang(request.env, prices[product.id], currency_obj=currency),
            "image": f"/web/image/product.product/{product.id}/image_128",
        } for product in products]})

    @route("/my/orders/<int:order_id>/favorite", type="http", auth="user", website=True, methods=["POST"])
    def int_order_favorite(self, order_id, name=None, redirect=None, **kwargs):
        back = self._int_back(redirect, "/my/orders")
        order = self._int_owned_order(order_id)
        if not order:
            return request.redirect(back)
        try:
            favorite = request.env["int.favorite.order"]._int_create_from_order(
                request.env.user, self._int_company(), order, name=name,
            )
        except UserError as exc:
            return self._int_error_redirect(back, exc)
        return request.redirect(self._int_with_param(back, "int_fav_saved", favorite.id))

    @route("/shop/cart/favorite", type="http", auth="user", website=True, methods=["POST"])
    def int_cart_favorite(self, name=None, **kwargs):
        cart = request.website._get_and_cache_current_cart()
        try:
            favorite = request.env["int.favorite.order"]._int_create_from_cart(
                request.env.user, self._int_company(), cart, name=name,
            )
        except UserError as exc:
            return self._int_error_redirect("/shop/cart", exc)
        return request.redirect(self._int_with_param("/shop/cart", "int_fav_saved", favorite.id))

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

    @route("/my/orders/<int:order_id>/cancel-backorder", type="http", auth="user", website=True, methods=["POST"])
    def int_order_cancel_backorder(self, order_id, reason="", note="", **kwargs):
        order = self._int_owned_order(order_id)
        if not order:
            return request.redirect("/my/orders")
        url = order.get_portal_url()
        separator = "&" if "?" in url else "?"
        try:
            outcome = order.int_portal_cancel_backorder(request.env.user, reason, note)
        except UserError as exc:
            return request.redirect(f"{url}{separator}int_error={quote(str(exc.args[0]))}")
        return request.redirect(f"{url}{separator}int_backorder={outcome}")

    @route("/my/po-template.xlsx", type="http", auth="user", website=True)
    def int_po_template(self, **kwargs):
        if not request.env.user.int_portal_can("upload_po"):
            return request.redirect("/my")
        content = request.env["sale.order"]._int_po_template_xlsx()
        return request.make_response(content, headers=[
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", "attachment; filename=po_template.xlsx"),
        ])

    def _int_po_filename(self, name, default):
        base = os.path.basename((name or "").replace("\\", "/")) 
        base = re.sub(r"[^\w.\- ]+", "", base).strip()[:120]
        return base or default

    def _int_po_drop_pending(self):
        pending = request.session.get("int_po_upload") or {}
        attachment_id = pending.get("attachment_id")
        if not attachment_id:
            return
        attachment = request.env["ir.attachment"].sudo().browse(attachment_id).exists()
        if attachment and not attachment.res_id:
            attachment.unlink()
        request.session.pop("int_po_upload", None)

    def _int_po_keep(self, raw, filename):
        self._int_po_drop_pending()
        attachment = request.env["ir.attachment"].sudo().create({
            "name": filename,
            "datas": base64.b64encode(raw),
            "type": "binary",
            "public": False,
        })
        return attachment

    def _int_po_review(self, error=""):
        pending = request.session.get("int_po_upload")
        if not pending:
            return request.redirect("/my/po-upload?error=%s" % quote(_("Upload the file again.")))
        cart = self._int_cart()
        lines = pending.get("lines") or []
        return request.render("int_sale_customizations.portal_po_review", {
            "page_name": "int_po",
            "int_error": error,
            "int_po_number": pending.get("po_number") or "",
            "int_lines": lines,
            "int_filename": pending.get("filename") or "",
            "int_is_pdf": pending.get("kind") == "pdf",
            "int_can_add": any(line.get("product_id") for line in lines),
            "int_cart_count": len(cart.order_line),
        })

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
        if not raw:
            return request.redirect("/my/po-upload?error=%s" % quote(_("Choose a file.")))
        if len(raw) > 10 * 1024 * 1024:
            return request.redirect("/my/po-upload?error=%s" % quote(_("The file must be 10 MB or smaller.")))
        filename = self._int_po_filename(upload.filename, "purchase-order")
        ext = os.path.splitext(filename)[1].lower()
        typed = (po_number or "").strip()[:80]
        SaleOrder = request.env["sale.order"]
        if ext == ".pdf":
            text = SaleOrder._int_po_text_from_pdf(raw)
            if not text.strip():
                return self._int_po_pdf(user, raw, filename, typed)
            try:
                po_from_file, lines = SaleOrder._int_po_review_from_text(text, request.website)
            except UserError as exc:
                return request.redirect("/my/po-upload?error=%s" % quote(str(exc.args[0])))
            kind = "pdf"
        elif ext == ".csv":
            try:
                po_from_file, parsed = SaleOrder._int_po_rows_from_csv(raw)
                lines = SaleOrder._int_po_review_lines(parsed, request.website)
            except UserError as exc:
                return request.redirect("/my/po-upload?error=%s" % quote(str(exc.args[0])))
            kind = "sheet"
        elif ext == ".xlsx":
            try:
                po_from_file, parsed = SaleOrder._int_po_rows_from_xlsx(raw)
                lines = SaleOrder._int_po_review_lines(parsed, request.website)
            except UserError as exc:
                return request.redirect("/my/po-upload?error=%s" % quote(str(exc.args[0])))
            kind = "sheet"
        else:
            return request.redirect("/my/po-upload?error=%s" % quote(_("Upload an .xlsx, .csv, or .pdf file.")))
        attachment = self._int_po_keep(raw, filename)
        request.session["int_po_upload"] = {
            "attachment_id": attachment.id,
            "filename": filename,
            "kind": kind,
            "po_number": typed or po_from_file or "",
            "lines": lines,
        }
        return self._int_po_review()

    @route("/my/po-upload/confirm", type="http", auth="user", website=True, methods=["POST"])
    def int_po_upload_confirm(self, po_number="", fresh="", **post):
        user = request.env.user
        if not user.int_portal_can("upload_po") or user.int_portal_ordering_blocked():
            return request.redirect("/my")
        pending = request.session.get("int_po_upload")
        if not pending:
            return request.redirect("/my/po-upload?error=%s" % quote(_("Upload the file again.")))
        SaleOrder = request.env["sale.order"]
        lines = []
        chosen = []
        problems = []
        for index, line in enumerate(pending.get("lines") or []):
            item = dict(line)
            raw_qty = post.get("qty_%s" % index, item.get("qty"))
            item["include"] = post.get("include_%s" % index) in ("on", "1", "true", "True")
            product = request.env["product.product"].browse(item.get("product_id") or 0).exists()
            if item["include"]:
                if not product or not SaleOrder._int_product_on_website(product, request.website):
                    item["reason"] = _("That product is no longer available.")
                    item["include"] = False
                    problems.append(item["sku"] or _("A line"))
                else:
                    quantity, reason = SaleOrder._int_po_quantity_for(product, raw_qty)
                    item["qty"] = quantity
                    item["reason"] = reason
                    if reason:
                        problems.append(item["sku"] or product.display_name)
                    else:
                        chosen.append((product, quantity))
            elif product:
                quantity, reason = SaleOrder._int_po_quantity_for(product, raw_qty)
                item["qty"] = quantity
                if reason:
                    item["reason"] = reason
            lines.append(item)
        pending = dict(pending)
        pending["lines"] = lines
        pending["po_number"] = (po_number or "").strip()[:80]
        request.session["int_po_upload"] = pending
        if problems:
            return self._int_po_review(error=_("Check these lines before adding them: %s", ", ".join(problems)))
        if not chosen:
            return self._int_po_review(error=_("Choose at least one product with a quantity."))
        cart = self._int_cart()
        if fresh == "1" and cart.order_line:
            cart.order_line.sudo().unlink()
        for product, quantity in chosen:
            cart._cart_add(product_id=product.id, quantity=quantity)
        values = {"int_uploaded_po": True}
        if pending["po_number"]:
            values["client_order_ref"] = pending["po_number"]
        cart.sudo().write(values)
        attachment = request.env["ir.attachment"].sudo().browse(pending.get("attachment_id")).exists()
        if attachment and not attachment.res_id:
            cart._int_po_keep_file(attachment)
        request.session.pop("int_po_upload", None)
        return request.redirect("/shop/cart")

    @route("/my/orders/<int:order_id>/po-file", type="http", auth="user", website=True)
    def int_po_file(self, order_id, **kwargs):
        order = request.env["sale.order"].browse(order_id).exists()
        user = request.env.user
        if not order or not user.int_portal_can("view_orders") or not order._int_owned_by(user):
            return request.redirect("/my")
        attachment = order._int_po_attachment()
        if not attachment or attachment.res_model != "sale.order" or attachment.res_id != order.id:
            return request.redirect(order.get_portal_url())
        filename = (attachment.name or "purchase-order").replace("\\", "").replace('"', "").replace("\r", "").replace("\n", "")
        return request.make_response(base64.b64decode(attachment.datas or b""), headers=[
            ("Content-Type", attachment.mimetype or "application/octet-stream"),
            ("Content-Disposition", "attachment; filename=\"%s\"" % filename),
        ])

    @route("/my/po-upload/staff", type="http", auth="user", website=True, methods=["POST"])
    def int_po_upload_staff(self, po_number="", **kwargs):
        user = request.env.user
        if not user.int_portal_can("upload_po"):
            return request.redirect("/my")
        pending = request.session.get("int_po_upload") or {}
        if pending.get("kind") != "pdf":
            return request.redirect("/my/po-upload")
        attachment = request.env["ir.attachment"].sudo().browse(pending.get("attachment_id")).exists()
        if not attachment or attachment.res_id:
            return request.redirect("/my/po-upload?error=%s" % quote(_("Upload the file again.")))
        raw = base64.b64decode(attachment.datas)
        number = (po_number or pending.get("po_number") or "").strip()[:80]
        request.session.pop("int_po_upload", None)
        return self._int_po_pdf(user, raw, attachment.name, number, attachment)

    def _int_po_pdf(self, user, raw, filename, po_number, attachment=None):
        website = request.website
        order = request.env["sale.order"].sudo().create({
            "partner_id": user.partner_id.id,
            "company_id": website.company_id.id,
            "website_id": website.id,
            "client_order_ref": (po_number or "").strip() or False,
            "int_uploaded_po": True,
        })
        if attachment is None:
            attachment = request.env["ir.attachment"].sudo().create({
                "name": filename or "purchase-order.pdf",
                "datas": base64.b64encode(raw),
                "type": "binary",
                "public": False,
            })
        order._int_po_keep_file(attachment)
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
