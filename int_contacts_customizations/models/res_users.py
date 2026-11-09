from odoo import models
from odoo.tools.image import image_data_uri


class ResUsers(models.Model):
    _inherit = "res.users"

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
