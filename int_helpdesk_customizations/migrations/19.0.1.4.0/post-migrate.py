"""Drop the unused Customer type ticket tags when nothing references them."""

from odoo import SUPERUSER_ID, api

UNUSED_TAGS = (
    "int_helpdesk_customizations.tag_customer_dealer",
    "int_helpdesk_customizations.tag_customer_retail",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Ticket = env["helpdesk.ticket"].with_context(active_test=False)
    for xmlid in UNUSED_TAGS:
        tag = env.ref(xmlid, raise_if_not_found=False)
        if not tag or Ticket.search_count([("tag_ids", "in", tag.ids)]):
            continue
        tag.unlink()
