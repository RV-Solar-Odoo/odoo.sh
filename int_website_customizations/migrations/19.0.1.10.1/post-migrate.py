"""Keep customers as the delivery contacts for in-store pickup orders."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    all_pickup_partners = env["res.partner"].with_context(active_test=False).search([
        ("is_pickup_location", "=", True),
    ])
    all_pickup_partners.modified(["name"])
    all_pickup_partners.flush_recordset(["complete_name"])

    orders = env["sale.order"].with_context(active_test=False).search([
        ("carrier_id.delivery_type", "=", "in_store"),
        ("partner_shipping_id.is_pickup_location", "=", True),
    ])
    if not orders:
        return

    pickup_partners = orders.partner_shipping_id
    express_partners = pickup_partners.parent_id.filtered(
        lambda partner: (
            partner.name
            and partner.name.startswith(
                "Anonymous express checkout partner for order "
            )
        )
    )

    for order in orders:
        fiscal_position = order.fiscal_position_id
        order.with_context(
            update_delivery_shipping_partner=True,
            tracking_disable=True,
            mail_notrack=True,
        ).write({
            "partner_shipping_id": order.partner_id.id,
            "fiscal_position_id": fiscal_position.id,
        })
        if "partner_shipping_id" in env["account.move"]._fields:
            order.invoice_ids.write({
                "partner_shipping_id": order.partner_id.id,
            })

    (pickup_partners | express_partners).write({"active": False})
