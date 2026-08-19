from odoo import fields, models


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
    country_of_origin = fields.Selection(
        [
            ("India", "India"),
            ("Malaysia", "Malaysia"),
            ("China", "China"),
        ],
        string="Country of Origin",
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
