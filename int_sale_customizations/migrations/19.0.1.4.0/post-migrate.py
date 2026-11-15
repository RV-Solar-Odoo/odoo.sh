import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Turn each starred order into a favorite named by its order number,
    shared by the dealer. The per-login star table is dropped after the update."""
    cr.execute("SELECT to_regclass('int_user_pinned_order_rel')")
    if not cr.fetchone()[0]:
        return
    cr.execute("SELECT DISTINCT order_id FROM int_user_pinned_order_rel")
    order_ids = [row[0] for row in cr.fetchall()]
    if not order_ids:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Favorite = env["int.favorite.order"].with_context(active_test=False)
    orders = env["sale.order"].browse(order_ids).exists().sorted("date_order", reverse=True)
    created = 0
    for order in orders:
        commercial = order.partner_id.commercial_partner_id
        company = order.company_id
        base = [("partner_id", "=", commercial.id), ("company_id", "=", company.id)]
        if Favorite.search_count(base + [("source_order_id", "=", order.id)]):
            continue
        if Favorite.search_count(base + [("active", "=", True)]) >= Favorite._int_limit(company):
            _logger.warning("Favorite orders: %s was starred but %s is at the limit.", order.name, commercial.name)
            continue
        items = Favorite._int_lines_to_items(order.order_line)
        if not items:
            continue
        Favorite._int_create_record(commercial, company, order.name, items, source_order=order)
        created += 1
    _logger.info("Favorite orders: %s created from starred orders.", created)
