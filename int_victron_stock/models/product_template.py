import logging
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

# Supplier stock above this is shown as "20+". Our own warehouse quantity is never capped.
VICTRON_PUBLIC_CAP = 20
LEAD_TIME_PHRASE = "within 7–10 days"

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    victron_sku = fields.Char(
        string="Victron SKU",
        groups="base.group_user",
        help="Victron article code used to match this product against the E-Order feed. "
             "Leave empty to fall back on the Internal SKU.",
    )
    victron_qty = fields.Float(
        string="Victron Stock",
        digits="Product Unit of Measure",
        readonly=True,
        copy=False,
        groups="base.group_user",
        help="Quantity Victron reports in stock. Informational only — it never creates quants "
             "and never affects valuation, reordering, or inventory reports.",
    )
    victron_last_sync = fields.Datetime(
        string="Victron Stock Changed",
        readonly=True,
        copy=False,
        groups="base.group_user",
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
        try:
            self._int_victron_sync_feed()
        except UserError as exc:
            _logger.warning("Victron sync skipped: %s", exc.args[0])
        except Exception:
            _logger.exception("Victron sync failed; keeping last known quantities.")

    @api.model
    def _int_victron_sync_feed(self):
        """Read E-Order stock for our SKUs only. Never creates warehouse stock."""
        icp = self.env["ir.config_parameter"].sudo()
        if icp.get_param("database.is_neutralized"):
            _logger.info("Victron sync skipped: database is neutralized.")
            return

        endpoint = icp.get_param("int_victron.endpoint") or "/products-stock/"
        sku_field = icp.get_param("int_victron.sku_field") or "sku"
        qty_field = icp.get_param("int_victron.qty_field") or "stock_quantity"
        api = self.env["int.victron.api"]
        products = self.with_context(active_test=False).search(
            ["|", ("victron_sku", "!=", False), ("default_code", "!=", False)]
        )
        skus = []
        seen = set()
        for product in products:
            sku = product._victron_effective_sku()
            if sku and sku not in seen:
                seen.add(sku)
                skus.append(sku)
        if not skus:
            _logger.info("Victron sync skipped: no products have a SKU.")
            return

        # Ask for each of our SKUs before writing anything. A throttle or outage
        # then leaves the last known quantities in place.
        rows = []
        stock_by_sku = {}
        for sku in skus:
            row = api.fetch_one(api._sku_path(endpoint, sku))
            if not row:
                stock_by_sku[sku] = 0.0
                continue
            reported = str(row.get(sku_field) or sku).strip().upper()
            try:
                stock_by_sku[reported] = float(row.get(qty_field) or 0)
            except (TypeError, ValueError):
                stock_by_sku[reported] = 0.0
            rows.append(row)

        now = fields.Datetime.now()
        by_qty = defaultdict(list)
        matched = 0
        for product in products:
            sku = product._victron_effective_sku()
            if not sku:
                continue
            qty = stock_by_sku.get(sku, 0.0)
            if qty:
                matched += 1
            if product.victron_qty != qty:
                by_qty[qty].append(product.id)

        for qty, ids in by_qty.items():
            self.browse(ids).write({"victron_qty": qty, "victron_last_sync": now})

        icp.set_param("int_victron.last_sync", fields.Datetime.to_string(now))
        self.env["int.victron.feed"]._replace_from_rows(rows, sku_field, qty_field)
        _logger.info(
            "Victron sync complete: %s SKUs requested, %s with stock, %s quantities changed.",
            len(skus),
            matched,
            sum(len(ids) for ids in by_qty.values()),
        )

    def _int_lead_phrase(self):
        phrase = (self.env["ir.config_parameter"].sudo().get_param("int_victron.lead_time_label") or "").strip()
        return phrase or LEAD_TIME_PHRASE

    def _int_format_qty(self, qty):
        qty = float(qty or 0.0)
        if abs(qty - round(qty)) < 1e-6:
            return str(int(round(qty)))
        return f"{qty:.2f}".rstrip("0").rstrip(".")

    def _int_public_victron_qty(self, qty):
        """Label for supplier stock. The exact figure never leaves this method."""
        if qty > VICTRON_PUBLIC_CAP:
            return f"{VICTRON_PUBLIC_CAP}+"
        return self._int_format_qty(qty)

    def _int_victron_feed_qty(self):
        self.ensure_one()
        return self.sudo().victron_qty or 0.0

    @api.model
    def _int_victron_clear_po_cache(self):
        if hasattr(self.env.cr, "int_victron_open_po_by_template"):
            del self.env.cr.int_victron_open_po_by_template

    @api.model
    def _int_victron_open_po_by_template(self):
        """Supplier quantity already promised on open Victron RFQs, by product template."""
        cached = getattr(self.env.cr, "int_victron_open_po_by_template", None)
        if cached is not None:
            return cached
        lines = self.env["purchase.order.line"].sudo().search([
            ("order_id.int_victron_rfq", "=", True),
            ("order_id.state", "in", ("draft", "sent", "purchase")),
            ("product_id", "!=", False),
        ])
        totals = defaultdict(float)
        for line in lines:
            remaining = max((line.product_qty or 0.0) - (line.qty_received or 0.0), 0.0)
            product_uom = line.product_id.uom_id
            if line.product_uom_id and line.product_uom_id != product_uom:
                remaining = line.product_uom_id._compute_quantity(remaining, product_uom)
            totals[line.product_id.product_tmpl_id.id] += remaining
        self.env.cr.int_victron_open_po_by_template = totals
        return totals

    def _int_victron_available_qty(self):
        """Supplier quantity we can still promise. Exact value, for server-side checks only."""
        self.ensure_one()
        promised = self._int_victron_open_po_by_template().get(self.id, 0.0)
        return max(self._int_victron_feed_qty() - promised, 0.0)

    def _int_own_available_qty(self, variant=None):
        """Quantity we can ship today from the website warehouse."""
        self.ensure_one()
        website = self.env["website"].get_current_website()
        if variant:
            return website._get_product_available_qty(variant.sudo())
        variants = self.sudo().product_variant_ids
        if not variants:
            return 0.0
        return sum(website._get_product_available_qty(item) for item in variants)

    def _int_can_order_online(self, variant=None):
        """True when the shop can sell this product from our warehouse or Victron."""
        self.ensure_one()
        if not self.is_storable:
            return True
        if self._int_own_available_qty(variant) > 0:
            return True
        return self._int_victron_available_qty() > 0

    def _website_show_quick_add(self):
        return super()._website_show_quick_add() and self._int_can_order_online()

    @api.model
    def _int_ships_domain(self, ships):
        """Storable products that ship "now" from our warehouse or "later" from Victron.

        Stock isn't searchable in SQL, so each storable product is checked with the same
        quantities its availability lines show.
        """
        storable = self.sudo().search([("is_storable", "=", True)])
        matching = storable.filtered(lambda template: (
            ("now" in ships and template._int_own_available_qty() > 0)
            or ("later" in ships and template._int_victron_available_qty() > 0)
        ))
        return Domain("id", "in", matching.ids)

    @api.model
    def _search_get_detail(self, website, order, options):
        detail = super()._search_get_detail(website, order, options)
        if options.get("int_ships"):
            detail["base_domain"].append(self._int_ships_domain(options["int_ships"]))
        return detail

    def _int_availability_lines(self, variant=None):
        """Shop labels. Own stock is exact. Victron stock is capped at 20+."""
        self.ensure_one()
        if not self.is_storable:
            return []
        if variant and (not variant.exists() or variant.product_tmpl_id != self):
            variant = None
        lines = []
        own = self._int_own_available_qty(variant)
        if own > 0:
            qty = self._int_format_qty(own)
            warehouse = self.env._("%(qty)s in stock — ships immediately", qty=qty)
            lines.append({
                "status": "immediate",
                "css": "text-bg-success",
                "icon": "fa-check",
                "detail": warehouse,
                "label": warehouse,
            })
        victron = self._int_victron_available_qty()
        if victron > 0:
            supplier = self.env._(
                "%(qty)s available — ships %(when)s",
                qty=self._int_public_victron_qty(victron),
                when=self._int_lead_phrase(),
            )
            lines.append({
                "status": "backup",
                "css": "text-bg-info",
                "icon": "fa-truck",
                "detail": supplier,
                "label": supplier,
            })
        if not lines:
            unavailable = self.env._("Currently unavailable — contact us for lead time")
            lines.append({
                "status": "unavailable",
                "css": "text-bg-secondary",
                "icon": "fa-clock-o",
                "detail": unavailable,
                "label": unavailable,
            })
        return lines

    def _get_additionnal_combination_info(self, product_or_template, quantity, uom, date, website):
        """Publish our own free quantity only, and let the server enforce Victron's real limit."""
        res = super()._get_additionnal_combination_info(
            product_or_template, quantity, uom, date, website
        )
        if not self.env.context.get("website_sale_stock_get_quantity"):
            return res
        if product_or_template.is_product_variant:
            template = product_or_template.product_tmpl_id
            variant = product_or_template
        else:
            template = product_or_template
            variant = None
        if not template.is_storable:
            return res
        res["int_availability_lines"] = template._int_availability_lines(variant)
        if not product_or_template.is_product_variant:
            return res
        # The browser uses free_qty as a hard cap. Keep that number equal to warehouse
        # stock (which we show) and turn the cap off when Victron can fill more, so a
        # customer can order 400 without the page telling them Victron's real count.
        # When neither side has any left, force the sold-out flag so Add to cart hides
        # even if the product is set to keep selling at zero.
        if not template._int_can_order_online(variant):
            res["allow_out_of_stock_order"] = False
        elif template._int_victron_available_qty() > 0:
            res["allow_out_of_stock_order"] = True
            res["show_availability"] = False
        return res
