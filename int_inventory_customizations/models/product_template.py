import logging
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    hts_code = fields.Char(string="HTS Code")
    vendor_name = fields.Char(string="Vendor")
    solar_panel_voltage = fields.Char(string="Solar Panel Voltage")
    inverter_battery_voltage = fields.Selection(
        [
            ("Voltage", "12v"),
            ("24v", "24v"),
            ("26", "36v"),
            ("48v", "48v"),
        ],
        string="Inverter Battery Voltage",
    )
    ac_input_voltage = fields.Selection(
        [
            ("120v", "120v"),
            ("120/240v", "120/240v"),
            ("230v", "230v"),
        ],
        string="AC Input Voltage",
    )
    ac_voltage_inverting = fields.Selection(
        [
            ("120v", "120v"),
            ("120/240v", "120/240v"),
            ("230v", "230v"),
        ],
        string="AC Voltage Inverting",
    )
    manufacturer = fields.Char(string="Manufacturer")
    map_price = fields.Monetary(string="MAP Price", currency_field="currency_id")
    gtin = fields.Char(string="GTIN")
    length_mm = fields.Float(string="Length (mm)")
    width_mm = fields.Float(string="Width (mm)")
    height_mm = fields.Float(string="Height (mm)")
    length_in = fields.Float(string="Length (in)")
    width_in = fields.Float(string="Width (in)")
    height_in = fields.Float(string="Height (in)")
    qty_per_pallet = fields.Float(string="Qty Per Pallet")
    battery_compatibility = fields.Selection(
        [
            ("12V", "12V"),
            ("24V", "24V"),
            ("12-24V", "12-24V"),
            ("12-48V", "12-48V"),
        ],
        string="Battery Compatibility",
    )
    ac_frequency = fields.Selection(
        [
            ("60Hz", "60Hz"),
            ("50Hz", "50Hz"),
            ("50/60Hz", "50/60Hz"),
        ],
        string="AC Frequency",
    )
    weight_lbs = fields.Float(string="Weight (lbs)")
    mppt_max_voltage = fields.Selection(
        [
            ("100V", "100V"),
            ("150V", "150V"),
        ],
        string="MPPT Max Voltage",
    )
    max_charge_amps = fields.Selection(
        [
            ("30A", "30A"),
            ("50A", "50A"),
            ("60A", "60A"),
            ("300A", "300A"),
        ],
        string="Max Charge Amps",
    )
    max_discharge_amps = fields.Selection(
        [
            ("300A", "300A"),
        ],
        string="Max Discharge Amps",
    )
    max_continuous_watts = fields.Selection(
        [
            ("1400W", "1400W"),
            ("2400W", "2400W"),
        ],
        string="Max Continuous Watts",
    )
    max_peak_watts = fields.Selection(
        [
            ("5.5kW", "5.5kW"),
            ("1400W", "1400W"),
        ],
        string="Max Peak Watts",
    )
    unused_yes_no = fields.Selection(
        [
            ("Yes", "Yes"),
            ("No", "No"),
        ],
        string="New Selection",
    )
    approved_for_boats = fields.Selection(
        [
            ("Yes", "Yes"),
            ("No", "No"),
        ],
        string="Approved for Boats",
    )
    approved_for_rvs = fields.Selection(
        [
            ("Yes", "Yes"),
            ("No", "No"),
        ],
        string="Approved for RVs",
    )
    approved_for_off_grid = fields.Selection(
        [
            ("Yes", "Yes"),
            ("No", "No"),
        ],
        string="Approved for Off Grid",
    )
    tariff = fields.Monetary(string="Tariff", currency_field="currency_id")
    tariff_cost = fields.Monetary(string="Tariff Cost", currency_field="currency_id")
    inbound_shipping_cost = fields.Monetary(
        string="Inbound Shipping Cost",
        currency_field="currency_id",
    )
    product_data_sheet = fields.Binary(string="Product Data Sheet")
    product_data_sheet_filename = fields.Char(string="Filename for Product Data Sheet")
    unused_checkbox = fields.Boolean(string="New CheckBox")
    certifications = fields.Selection(
        [
            ("UL458", "UL 458"),
            ("UL1746", "UL 1746"),
        ],
        string="Certifications",
    )
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
