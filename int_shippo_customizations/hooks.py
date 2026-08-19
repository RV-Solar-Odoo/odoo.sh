"""Create placeholder carton package types in the database length/weight UoM."""


def _inches_to_system(env, inches):
    name = (env["product.template"]._get_length_uom_name_from_ir_config_parameter() or "").lower()
    if name in ("in", "inch", "inches", '"'):
        return inches
    if "mm" in name:
        return inches * 25.4
    if "cm" in name:
        return inches * 2.54
    if "ft" in name or "foot" in name or "feet" in name:
        return inches / 12.0
    return inches * 0.0254


def _lb_to_system(env, pounds):
    name = (env["product.template"]._get_weight_uom_name_from_ir_config_parameter() or "").lower()
    if name in ("lb", "lbs", "pound", "pounds"):
        return pounds
    if "oz" in name:
        return pounds * 16.0
    if name in ("g", "gram", "grams"):
        return pounds * 453.592
    return pounds / 2.20462


def ensure_package_types(env):
    PackageType = env["stock.package.type"].sudo()
    boxes = [
        ("int_shippo_box_small", "Small Carton", 12.0, 10.0, 8.0, 0.5, 20.0),
        ("int_shippo_box_medium", "Medium Carton", 18.0, 14.0, 12.0, 1.0, 40.0),
        ("int_shippo_box_large", "Large Carton", 24.0, 18.0, 16.0, 1.5, 70.0),
    ]
    for xmlid, name, length_in, width_in, height_in, empty_lb, max_lb in boxes:
        existing = env.ref(f"int_shippo_customizations.{xmlid}", raise_if_not_found=False)
        if existing:
            continue
        record = PackageType.create({
            "name": name,
            "packaging_length": _inches_to_system(env, length_in),
            "width": _inches_to_system(env, width_in),
            "height": _inches_to_system(env, height_in),
            "base_weight": _lb_to_system(env, empty_lb),
            "max_weight": _lb_to_system(env, max_lb),
            "package_use": "disposable",
            "sequence_code": xmlid.split("_")[-1][:3].upper(),
        })
        env["ir.model.data"].sudo().create({
            "name": xmlid,
            "module": "int_shippo_customizations",
            "model": "stock.package.type",
            "res_id": record.id,
            "noupdate": True,
        })
