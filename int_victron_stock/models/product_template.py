import logging
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    victron_sku = fields.Char(
        string="Victron SKU",
        help="Victron article code used to match this product against the E-Order feed. "
             "Leave empty to fall back on the Internal SKU.",
    )
    victron_qty = fields.Float(
        string="Victron Stock",
        digits="Product Unit of Measure",
        readonly=True,
        copy=False,
        help="Quantity Victron reports in stock. Informational only — it never creates quants "
             "and never affects valuation, reordering, or inventory reports.",
    )
    victron_last_sync = fields.Datetime(
        string="Victron Stock Changed",
        readonly=True,
        copy=False,
        help="Last time the E-Order feed reported a different quantity for this product.",
    )

    def _victron_effective_sku(self):
        self.ensure_one()
        return (self.victron_sku or self.default_code or "").strip().upper()

    @api.model
    def cron_sync_victron_stock(self):
        """Store Victron E-Order stock levels on matching products.

        A failure here must never take the webshop down, so every error path keeps the
        last known quantities and only logs.
        """
        icp = self.env["ir.config_parameter"].sudo()
        if icp.get_param("database.is_neutralized"):
            _logger.info("Victron sync skipped: database is neutralized.")
            return

        endpoint = icp.get_param("int_victron.endpoint") or "/products-extended/"
        sku_field = icp.get_param("int_victron.sku_field") or "sku"
        qty_field = icp.get_param("int_victron.qty_field") or "stock"

        try:
            rows = self.env["int.victron.api"].fetch_all(endpoint)
        except UserError as exc:
            _logger.warning("Victron sync skipped: %s", exc.args[0])
            return
        except Exception:
            _logger.exception("Victron sync failed; keeping last known quantities.")
            return

        stock_by_sku = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = str(row.get(sku_field) or "").strip().upper()
            if not sku:
                continue
            try:
                stock_by_sku[sku] = float(row.get(qty_field) or 0)
            except (TypeError, ValueError):
                stock_by_sku[sku] = 0.0

        if not stock_by_sku:
            _logger.warning(
                "Victron sync: %s rows returned but none usable. Check the SKU and quantity "
                "field names under Inventory → Settings → Victron E-Order.",
                len(rows),
            )
            return

        products = self.with_context(active_test=False).search(
            ["|", ("victron_sku", "!=", False), ("default_code", "!=", False)]
        )
        now = fields.Datetime.now()
        by_qty = defaultdict(list)
        matched = 0
        for product in products:
            qty = stock_by_sku.get(product._victron_effective_sku())
            if qty is None:
                # Absent from the feed means Victron no longer stocks it.
                qty = 0.0
            else:
                matched += 1
            if product.victron_qty != qty:
                by_qty[qty].append(product.id)

        for qty, ids in by_qty.items():
            self.browse(ids).write({"victron_qty": qty, "victron_last_sync": now})

        icp.set_param("int_victron.last_sync", fields.Datetime.to_string(now))
        _logger.info(
            "Victron sync complete: %s API rows, %s products matched, %s quantities changed.",
            len(stock_by_sku),
            matched,
            sum(len(ids) for ids in by_qty.values()),
        )

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
