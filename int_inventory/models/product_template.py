from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_studio_hts_code = fields.Char(string="HTS Code")
    x_studio_vendor = fields.Char(string="Vendor")
    x_studio_solar_panel_voltage = fields.Char(string="Solar Panel Voltage")
    x_studio_voltage = fields.Selection(
        [
            ("Voltage", "12v"),
            ("24v", "24v"),
            ("26", "36v"),
            ("48v", "48v"),
        ],
        string="Inverter Battery Voltage",
    )
    x_studio_ac_input_voltage = fields.Selection(
        [
            ("120v", "120v"),
            ("120/240v", "120/240v"),
            ("230v", "230v"),
        ],
        string="AC Input Voltage",
    )
    x_studio_ac_voltage_inverting = fields.Selection(
        [
            ("120v", "120v"),
            ("120/240v", "120/240v"),
            ("230v", "230v"),
        ],
        string="AC Voltage Inverting",
    )
    x_studio_manufacturer = fields.Char(string="Manufacturer")
    x_studio_map_price = fields.Monetary(string="MAP Price", currency_field="currency_id")
    x_studio_gtin = fields.Char(string="GTIN")
    x_studio_length_mm = fields.Float(string="Length (mm)")
    x_studio_width_mm = fields.Float(string="Width (mm)")
    x_studio_height_mm = fields.Float(string="Height (mm)")
    x_studio_length_in = fields.Float(string="Length (in)")
    x_studio_width_in = fields.Float(string="Width (in)")
    x_studio_height_in = fields.Float(string="Height (in)")
    x_studio_qty_per_pallet = fields.Float(string="Qty Per Pallet")
    x_studio_battery_compatibility = fields.Selection(
        [
            ("12V", "12V"),
            ("24V", "24V"),
            ("12-24V", "12-24V"),
            ("12-48V", "12-48V"),
        ],
        string="Battery Compatibility",
    )
    x_studio_ac_frequency = fields.Selection(
        [
            ("60Hz", "60Hz"),
            ("50Hz", "50Hz"),
            ("50/60Hz", "50/60Hz"),
        ],
        string="AC Frequency",
    )
    x_studio_weight_lbs = fields.Float(string="Weight (lbs)")
    x_studio_mppt_max_voltage = fields.Selection(
        [
            ("100V", "100V"),
            ("150V", "150V"),
        ],
        string="MPPT Max Voltage",
    )
    x_studio_max_charge_amps = fields.Selection(
        [
            ("30A", "30A"),
            ("50A", "50A"),
            ("60A", "60A"),
            ("300A", "300A"),
        ],
        string="Max Charge Amps",
    )
    x_studio_max_discharge_amps = fields.Selection(
        [
            ("300A", "300A"),
        ],
        string="Max Discharge Amps",
    )
    x_studio_max_continuous_watts = fields.Selection(
        [
            ("1400W", "1400W"),
            ("2400W", "2400W"),
        ],
        string="Max Continuous Watts",
    )
    x_studio_max_peak_watts = fields.Selection(
        [
            ("5.5kW", "5.5kW"),
            ("1400W", "1400W"),
        ],
        string="Max Peak Watts",
    )
    x_studio_selection_field_42f_1jpp20kml = fields.Selection(
        [
            ("Yes", "Yes"),
            ("No", "No"),
        ],
        string="New Selection",
    )
    x_studio_approved_for_boats = fields.Selection(
        [
            ("Yes", "Yes"),
            ("No", "No"),
        ],
        string="Approved for Boats",
    )
    x_studio_approved_for_rvs = fields.Selection(
        [
            ("Yes", "Yes"),
            ("No", "No"),
        ],
        string="Approved for RVs",
    )
    x_studio_approved_for_off_grid = fields.Selection(
        [
            ("Yes", "Yes"),
            ("No", "No"),
        ],
        string="Approved for Off Grid",
    )
    x_studio_country_of_origin = fields.Selection(
        [
            ("India", "India"),
            ("Malaysia", "Malaysia"),
            ("China", "China"),
        ],
        string="Country of Origin",
    )
    x_studio_tariff = fields.Monetary(string="Tariff", currency_field="currency_id")
    x_studio_tariff_cost = fields.Monetary(string="Tariff Cost", currency_field="currency_id")
    x_studio_inbound_shipping_cost = fields.Monetary(
        string="Inbound Shipping Cost",
        currency_field="currency_id",
    )
    x_studio_product_data_sheet = fields.Binary(string="Product Data Sheet")
    x_studio_product_data_sheet_filename = fields.Char(
        string="Filename for Product Data Sheet",
    )
    x_studio_boolean_field_4p2_1jq6t615h = fields.Boolean(string="New CheckBox")
    x_studio_certifications = fields.Selection(
        [
            ("UL458", "UL 458"),
            ("UL1746", "UL 1746"),
        ],
        string="Certifications",
    )
