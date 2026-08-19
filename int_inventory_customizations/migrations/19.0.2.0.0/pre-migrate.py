"""Rename Studio columns before ORM recreates empty fields."""

from odoo.tools.sql import column_exists

# old Studio name -> new Python field name
FIELD_RENAMES = [
    ("x_studio_hts_code", "hts_code"),
    ("x_studio_vendor", "vendor_name"),
    ("x_studio_solar_panel_voltage", "solar_panel_voltage"),
    ("x_studio_voltage", "inverter_battery_voltage"),
    ("x_studio_ac_input_voltage", "ac_input_voltage"),
    ("x_studio_ac_voltage_inverting", "ac_voltage_inverting"),
    ("x_studio_manufacturer", "manufacturer"),
    ("x_studio_map_price", "map_price"),
    ("x_studio_gtin", "gtin"),
    ("x_studio_length_mm", "length_mm"),
    ("x_studio_width_mm", "width_mm"),
    ("x_studio_height_mm", "height_mm"),
    ("x_studio_length_in", "length_in"),
    ("x_studio_width_in", "width_in"),
    ("x_studio_height_in", "height_in"),
    ("x_studio_qty_per_pallet", "qty_per_pallet"),
    ("x_studio_battery_compatibility", "battery_compatibility"),
    ("x_studio_ac_frequency", "ac_frequency"),
    ("x_studio_weight_lbs", "weight_lbs"),
    ("x_studio_mppt_max_voltage", "mppt_max_voltage"),
    ("x_studio_max_charge_amps", "max_charge_amps"),
    ("x_studio_max_discharge_amps", "max_discharge_amps"),
    ("x_studio_max_continuous_watts", "max_continuous_watts"),
    ("x_studio_max_peak_watts", "max_peak_watts"),
    ("x_studio_selection_field_42f_1jpp20kml", "unused_yes_no"),
    ("x_studio_approved_for_boats", "approved_for_boats"),
    ("x_studio_approved_for_rvs", "approved_for_rvs"),
    ("x_studio_approved_for_off_grid", "approved_for_off_grid"),
    ("x_studio_country_of_origin", "country_of_origin"),
    ("x_studio_tariff", "tariff"),
    ("x_studio_tariff_cost", "tariff_cost"),
    ("x_studio_inbound_shipping_cost", "inbound_shipping_cost"),
    ("x_studio_product_data_sheet", "product_data_sheet"),
    ("x_studio_product_data_sheet_filename", "product_data_sheet_filename"),
    ("x_studio_boolean_field_4p2_1jq6t615h", "unused_checkbox"),
    ("x_studio_certifications", "certifications"),
]


def migrate(cr, version):
    if not version:
        return
    for old, new in FIELD_RENAMES:
        old_col = column_exists(cr, "product_template", old)
        new_col = column_exists(cr, "product_template", new)
        if old_col and not new_col:
            cr.execute(f'ALTER TABLE product_template RENAME COLUMN "{old}" TO "{new}"')
        elif old_col and new_col:
            cr.execute(
                f'UPDATE product_template SET "{new}" = "{old}" WHERE "{new}" IS NULL AND "{old}" IS NOT NULL'
            )
        cr.execute(
            """
            UPDATE ir_model_fields
               SET name = %s
             WHERE name = %s
               AND model IN ('product.template', 'product.product')
            """,
            (new, old),
        )
        cr.execute(
            """
            UPDATE ir_attachment
               SET res_field = %s
             WHERE res_field = %s
               AND res_model IN ('product.template', 'product.product')
            """,
            (new, old),
        )
        for model_xml in ("product_template", "product_product"):
            cr.execute(
                """
                UPDATE ir_model_data
                   SET name = %s
                 WHERE module = 'int_inventory_customizations'
                   AND model = 'ir.model.fields'
                   AND name = %s
                """,
                (f"field_{model_xml}__{new}", f"field_{model_xml}__{old}"),
            )
