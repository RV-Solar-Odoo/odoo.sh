from odoo import api, fields, models
from odoo.exceptions import AccessError


class VictronFeed(models.Model):
    """Last E-Order catalog. These rows are not stock quants and never enter our warehouse."""

    _name = "int.victron.feed"
    _description = "Victron E-Order stock"
    _order = "qty desc, sku"
    _rec_name = "sku"

    sku = fields.Char(required=True, index=True)
    name = fields.Char(string="Description")
    qty = fields.Float(
        string="Victron Stock",
        digits="Product Unit of Measure",
        help="Quantity Victron reported. It is not on-hand stock in our warehouse.",
    )
    additional_qty = fields.Float(
        string="Additional Stock",
        digits="Product Unit of Measure",
        help="Extra quantity Victron reported, usually at another of their warehouses.",
    )
    product_id = fields.Many2one(
        "product.template",
        string="Our Product",
        index=True,
        help="Our catalog item with this SKU. Empty when Victron stocks something we do not sell.",
    )
    synced_at = fields.Datetime(string="Fetched", readonly=True)

    @api.model
    def _replace_from_rows(self, rows, sku_field, qty_field):
        """Replace this list with one snapshot of the feed. Does not create quants."""
        parsed = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = str(row.get(sku_field) or "").strip().upper()
            if not sku:
                continue
            try:
                qty = float(row.get(qty_field) or 0)
            except (TypeError, ValueError):
                qty = 0.0
            try:
                additional = float(row.get("additional_stock_quantity") or 0)
            except (TypeError, ValueError):
                additional = 0.0
            parsed[sku] = {
                "sku": sku,
                "name": (str(row.get("description") or row.get("name") or "")[:256] or False),
                "qty": qty,
                "additional_qty": additional,
            }

        products = self.env["product.template"].sudo().with_context(active_test=False).search(
            ["|", ("victron_sku", "!=", False), ("default_code", "!=", False)]
        )
        by_sku = {}
        for product in products:
            code = product._victron_effective_sku()
            if code and code not in by_sku:
                by_sku[code] = product.id

        now = fields.Datetime.now()
        self.sudo().search([]).unlink()
        if not parsed:
            return
        self.sudo().create([
            {
                **vals,
                "product_id": by_sku.get(sku),
                "synced_at": now,
            }
            for sku, vals in parsed.items()
        ])

    def action_refresh(self):
        """Pull the feed now. Warehouse stock is left untouched."""
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(self.env._("Only an inventory manager can refresh Victron stock."))
        self.env["product.template"].sudo()._int_victron_sync_feed()
        return self.env["ir.actions.act_window"]._for_xml_id(
            "int_victron_stock.action_int_victron_feed"
        )
