from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _int_own_available_qty(self):
        """Quantity we can ship today from the website warehouse."""
        self.ensure_one()
        website = self.env["website"].get_current_website()
        variants = self.sudo().product_variant_ids
        if not variants:
            return 0.0
        return sum(website._get_product_available_qty(variant) for variant in variants)

    def _int_shipping_badge(self):
        """Return the availability badge shown on the shop, or False to show nothing."""
        self.ensure_one()
        if not self.is_storable:
            return False
        if self._int_own_available_qty() > 0:
            return {
                "status": "immediate",
                "css": "text-bg-success",
                "icon": "fa-check",
                "label": self.env._("In stock — ships immediately"),
            }
        if self.sudo().victron_qty > 0:
            icp = self.env["ir.config_parameter"].sudo()
            return {
                "status": "backup",
                "css": "text-bg-info",
                "icon": "fa-truck",
                "label": icp.get_param("int_victron.lead_time_label")
                or self.env._("Ships in about 2 weeks"),
            }
        return {
            "status": "unavailable",
            "css": "text-bg-secondary",
            "icon": "fa-clock-o",
            "label": self.env._("Currently unavailable — contact us for lead time"),
        }
