"""Name the delivery product Shipping fee.

The product was created from a noupdate file as Shippo Shipping, which is
what sales orders show on the delivery line. An upgrade does not rewrite
that record, so this does.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    product = env.ref(
        "int_shippo_customizations.product_product_delivery_shippo",
        raise_if_not_found=False,
    )
    if not product:
        return
    product.name = "Shipping fee"
    lines = env["sale.order.line"].search([
        ("product_id", "=", product.id),
        ("name", "ilike", "Shippo Shipping"),
    ])
    for line in lines:
        line.name = line.name.replace("Shippo Shipping", "Shipping fee")
    moves = env["account.move.line"].search([
        ("product_id", "=", product.id),
        ("name", "ilike", "Shippo Shipping"),
    ])
    for move in moves:
        move.name = move.name.replace("Shippo Shipping", "Shipping fee")
