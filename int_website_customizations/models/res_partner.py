from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_complete_name(self):
        """Name a store pickup for the shop, not the contact it was filed under.

        Click & Collect files the store as a child of whatever delivery contact
        was on the order. Express checkout's placeholder
        ("Anonymous express checkout partner for order ...") then shows up in
        front of the shop name. The shop name stays on the contact. A parent
        with no street is only there to hold that label, so it is left as-is.
        """
        self.ensure_one()
        if self.is_pickup_location and self.name and (self.street or self.city or self.zip):
            return self.env._("In-Store Pickup, %s", self.name)
        return super()._get_complete_name()
