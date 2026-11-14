from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

# One table for every portal check. Owner can do all of these.
INT_PORTAL_PERMISSIONS = {
    "view_orders": {"owner", "buyer", "accountant", "viewer"},
    "place_orders": {"owner", "buyer"},
    "cancel_orders": {"owner", "buyer"},
    "pin_orders": {"owner", "buyer"},
    "upload_po": {"owner", "buyer"},
    "export_orders": {"owner", "buyer", "accountant"},
    "manage_addresses": {"owner", "buyer"},
    "view_invoices": {"owner", "accountant"},
    "make_payments": {"owner", "accountant"},
    "view_credit": {"owner", "accountant"},
    "view_store_credit": {"owner", "accountant"},
    "manage_certificates": {"owner", "accountant"},
    "export_pricing": {"owner"},
    "view_resources": {"owner", "buyer", "accountant", "viewer"},
    "submit_tickets": {"owner", "buyer", "accountant"},
    "create_quotes": {"owner", "buyer"},
    "manage_users": {"owner"},
}


class ResUsers(models.Model):
    _inherit = "res.users"

    int_session_epoch = fields.Integer(
        default=0,
        copy=False,
        help="Raised when the portal role changes so the old session cannot keep the previous permissions.",
    )
    int_portal_role = fields.Selection(
        related="partner_id.int_portal_role",
        store=True,
        readonly=True,
    )

    @api.model
    def _get_session_token_fields(self):
        return super()._get_session_token_fields() | {"int_session_epoch"}

    def int_portal_role_value(self):
        self.ensure_one()
        if self._is_public():
            return False
        if self.has_group("base.group_user"):
            return "owner"
        return self.partner_id.sudo().int_portal_role or "owner"

    def int_portal_can(self, permission):
        """True when this user may do `permission` in My Portal."""
        self.ensure_one()
        if self._is_public():
            return False
        if self.has_group("base.group_user"):
            return True
        allowed = INT_PORTAL_PERMISSIONS.get(permission)
        if not allowed:
            return False
        return self.int_portal_role_value() in allowed

    def int_portal_ordering_blocked(self):
        """Portal users who cannot place orders. Retail visitors and staff are not blocked."""
        self.ensure_one()
        if self._is_public() or not self.share:
            return False
        return not self.int_portal_can("place_orders")

    def int_portal_set_role(self, role, actor):
        """Change this login's role. The last owner cannot be demoted or disabled."""
        self.ensure_one()
        if role not in dict(self.partner_id._fields["int_portal_role"].selection):
            raise UserError(_("Choose a role."))
        commercial = self.partner_id.commercial_partner_id
        current = self.partner_id.int_portal_role or "owner"
        if current == "owner" and role != "owner" and self.active and commercial._int_portal_owner_count() <= 1:
            raise UserError(_("This is the last owner. Add another owner before changing this role."))
        self.partner_id.sudo().write({"int_portal_role": role})
        self.sudo().write({"int_session_epoch": (self.int_session_epoch or 0) + 1})
        commercial.message_post(body=_(
            "%(actor)s set %(user)s to %(role)s.",
            actor=actor.name,
            user=self.name,
            role=dict(self.partner_id._fields["int_portal_role"].selection)[role],
        ))

    def int_portal_set_active(self, active, actor):
        self.ensure_one()
        commercial = self.partner_id.commercial_partner_id
        if not active and (self.partner_id.int_portal_role or "owner") == "owner" and commercial._int_portal_owner_count() <= 1:
            raise UserError(_("This is the last owner. Add another owner before disabling this login."))
        self.sudo().write({
            "active": bool(active),
            "int_session_epoch": (self.int_session_epoch or 0) + 1,
        })
        commercial.message_post(body=_(
            "%(actor)s %(action)s %(user)s.",
            actor=actor.name,
            action=_("enabled") if active else _("disabled"),
            user=self.name,
        ))

    def _int_portal_sales_rep(self):
        """The commercial partner's salesperson, or False when none is assigned."""
        self.ensure_one()
        if self._is_public():
            return False
        commercial = self.partner_id.commercial_partner_id
        rep_user = commercial.user_id
        if not rep_user:
            return False
        rep = rep_user.partner_id.sudo()
        phone = False
        for field_name in ("work_phone", "phone", "mobile"):
            if field_name in rep._fields and rep[field_name]:
                phone = rep[field_name]
                break
        digits = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
        image = rep.avatar_128
        return {
            "name": rep.name or rep_user.name,
            "email": rep.email or rep_user.email or False,
            "phone": phone or False,
            "phone_href": f"tel:{digits}" if digits else False,
            "image": image_data_uri(image) if image else False,
        }
