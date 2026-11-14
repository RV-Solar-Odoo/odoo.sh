import csv
import io
from datetime import date
from urllib.parse import quote

from odoo.exceptions import UserError
from odoo.http import request, route

from odoo.addons.portal.controllers.portal import CustomerPortal


def _address_match(partner, query):
    if not query:
        return True
    haystack = " ".join(
        part for part in (partner.name, partner.street, partner.street2, partner.city, partner.zip) if part
    ).lower()
    return query.lower() in haystack


class CustomerPortal(CustomerPortal):

    def _parse_form_data(self, form_data):
        data = dict(form_data)
        for key in ("int_has_loading_dock", "int_has_forklift"):
            if key in data:
                data[key] = data[key] in (True, "1", "true", "True", "on")
        return super()._parse_form_data(data)

    def _prepare_address_data(self, partner_sudo, **kwargs):
        data = super()._prepare_address_data(partner_sudo, **kwargs)
        delivery = data.get("delivery_addresses") or request.env["res.partner"]
        business_query = (kwargs.get("business_search") or "").strip()
        customer_query = (kwargs.get("customer_search") or "").strip()
        business = delivery.filtered(
            lambda partner: partner.int_address_category != "customer" and _address_match(partner, business_query)
        )
        customers = delivery.filtered(
            lambda partner: partner.int_address_category == "customer" and _address_match(partner, customer_query)
        )
        show_all = kwargs.get("show") == "all"
        data.update({
            "business_count": len(business),
            "customer_count": len(customers),
            "business_addresses": business if show_all else business[:20],
            "customer_addresses": customers if show_all else customers[:20],
            "business_search": business_query,
            "customer_search": customer_query,
            "int_addresses_truncated": not show_all and (len(business) > 20 or len(customers) > 20),
            "int_can_manage_addresses": request.env.user.int_portal_can("manage_addresses"),
        })
        return data

    def _int_address_family_ok(self, partner):
        user = request.env.user
        if partner.commercial_partner_id != user.partner_id.commercial_partner_id:
            return False
        return user.int_portal_can("manage_addresses")

    @route("/my/address/category", type="http", auth="user", website=True, methods=["POST"])
    def int_address_category(self, partner_id, category, **kwargs):
        partner = request.env["res.partner"].sudo().browse(int(partner_id)).exists()
        if not partner or not self._int_address_family_ok(partner):
            return request.redirect("/my/addresses")
        if category not in ("business", "customer"):
            return request.redirect("/my/addresses")
        try:
            partner.write({"int_address_category": category})
        except UserError:
            return request.redirect("/my/addresses")
        return request.redirect("/my/addresses")

    @route("/my/address/submit", type="http", methods=["POST"], auth="user", website=True, sitemap=False)
    def portal_address_submit(self, partner_id=None, **form_data):
        if not request.env.user.int_portal_can("manage_addresses"):
            return request.redirect("/my/addresses")
        return super().portal_address_submit(partner_id=partner_id, **form_data)

    @route("/my/address/archive", type="jsonrpc", auth="user", website=True, methods=["POST"])
    def address_archive(self, partner_id):
        if not request.env.user.int_portal_can("manage_addresses"):
            return
        return super().address_archive(partner_id)

    @route("/my/users", type="http", auth="user", website=True)
    def int_portal_users(self, **kwargs):
        user = request.env.user
        if not user.int_portal_can("manage_users"):
            return request.redirect("/my")
        commercial = user.partner_id.commercial_partner_id
        users = commercial._int_portal_family_users().sorted(lambda portal_user: (not portal_user.active, portal_user.name or ""))
        return request.render("int_contacts_customizations.portal_users", {
            "page_name": "int_users",
            "int_users": users,
            "int_roles": user.partner_id._fields["int_portal_role"].selection,
            "int_error": kwargs.get("error") or "",
        })

    @route("/my/users/invite", type="http", auth="user", website=True, methods=["POST"])
    def int_portal_users_invite(self, name="", email="", role="buyer", **kwargs):
        user = request.env.user
        if not user.int_portal_can("manage_users"):
            return request.redirect("/my")
        try:
            user.partner_id.commercial_partner_id.int_portal_invite_user(name, email, role)
        except UserError as exc:
            return request.redirect("/my/users?error=%s" % quote(str(exc.args[0])))
        return request.redirect("/my/users")

    @route("/my/users/<int:user_id>/role", type="http", auth="user", website=True, methods=["POST"])
    def int_portal_users_role(self, user_id, role, **kwargs):
        actor = request.env.user
        if not actor.int_portal_can("manage_users"):
            return request.redirect("/my")
        target = self._int_family_user(user_id)
        if not target:
            return request.redirect("/my/users")
        try:
            target.int_portal_set_role(role, actor)
        except UserError as exc:
            return request.redirect("/my/users?error=%s" % quote(str(exc.args[0])))
        return request.redirect("/my/users")

    @route("/my/users/<int:user_id>/active", type="http", auth="user", website=True, methods=["POST"])
    def int_portal_users_active(self, user_id, active="0", **kwargs):
        actor = request.env.user
        if not actor.int_portal_can("manage_users"):
            return request.redirect("/my")
        target = self._int_family_user(user_id)
        if not target:
            return request.redirect("/my/users")
        try:
            target.int_portal_set_active(active == "1", actor)
        except UserError as exc:
            return request.redirect("/my/users?error=%s" % quote(str(exc.args[0])))
        return request.redirect("/my/users")

    @route("/my/users/<int:user_id>/resend", type="http", auth="user", website=True, methods=["POST"])
    def int_portal_users_resend(self, user_id, **kwargs):
        actor = request.env.user
        if not actor.int_portal_can("manage_users"):
            return request.redirect("/my")
        target = self._int_family_user(user_id)
        if target:
            target.partner_id._int_send_dealer_account_email()
        return request.redirect("/my/users")

    @route("/my/addresses/export", type="http", auth="user", website=True)
    def int_addresses_export(self, export_format="xlsx", **kwargs):
        user = request.env.user
        if not user.int_portal_can("manage_addresses"):
            return request.redirect("/my/addresses")
        commercial = user.partner_id.commercial_partner_id
        partners = commercial._int_portal_family_partners().filtered(
            lambda partner: partner == commercial or partner.type != "contact" or partner.street
        )
        header = [
            "Name", "Category", "Commercial/Residential", "Dock", "Forklift",
            "Street", "Street 2", "City", "State", "ZIP", "Country", "Phone", "Email",
        ]
        rows = []
        for partner in partners:
            rows.append([
                partner.name or "",
                partner.int_address_category or "",
                partner.int_location_type or "",
                "Yes" if partner.int_has_loading_dock else "No",
                "Yes" if partner.int_has_forklift else "No",
                partner.street or "",
                partner.street2 or "",
                partner.city or "",
                partner.state_id.code or "",
                partner.zip or "",
                partner.country_id.code or "",
                partner.phone or "",
                partner.email or "",
            ])
        stamp = date.today().isoformat()
        if export_format == "csv":
            buffer = io.StringIO()
            buffer.write("\ufeff")
            writer = csv.writer(buffer)
            writer.writerow(header)
            writer.writerows(rows)
            content = buffer.getvalue().encode("utf-8")
            filename = f"addresses_{stamp}.csv"
            mimetype = "text/csv"
        else:
            import xlsxwriter
            buffer = io.BytesIO()
            workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
            sheet = workbook.add_worksheet("Addresses")
            for column, title in enumerate(header):
                sheet.write(0, column, title)
            for row_index, row in enumerate(rows, start=1):
                for column, value in enumerate(row):
                    sheet.write(row_index, column, value)
            workbook.close()
            content = buffer.getvalue()
            filename = f"addresses_{stamp}.xlsx"
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return request.make_response(content, headers=[
            ("Content-Type", mimetype),
            ("Content-Disposition", f"attachment; filename={filename}"),
        ])

    def _int_family_user(self, user_id):
        actor = request.env.user
        target = request.env["res.users"].sudo().with_context(active_test=False).browse(user_id).exists()
        family = actor.partner_id.commercial_partner_id._int_portal_family_users()
        if not target or target not in family:
            return request.env["res.users"]
        return target
