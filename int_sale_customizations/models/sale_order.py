from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _int_portal_shipments(self):
        """Tracking for each order, read from the pickings already on those orders.

        One pass over the outgoing shipments. Cancelled shipments are left out.
        ``partial`` is true when something has shipped and something is still open.
        """
        pickings = self.picking_ids.filtered(
            lambda picking: picking.picking_type_code == "outgoing" and picking.state != "cancel"
        )
        pickings.mapped("carrier_tracking_ref")
        pickings.mapped("carrier_tracking_url")
        pickings.mapped("carrier_id")
        grouped = {}
        for picking in pickings.sorted("id"):
            grouped.setdefault(picking.sale_id.id, []).append(picking)
        result = {}
        for order in self:
            rows = []
            links = []
            shipped = False
            still_open = False
            for picking in grouped.get(order.id, []):
                picking_links = picking._int_portal_tracking_links()
                done = picking.state == "done"
                if done:
                    shipped = True
                    links.extend(picking_links)
                else:
                    still_open = True
                rows.append({
                    "name": picking.name,
                    "done": done,
                    "links": picking_links,
                })
            result[order.id] = {
                "links": links,
                "partial": shipped and still_open,
                "shipments": rows,
            }
        return result
