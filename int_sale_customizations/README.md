# Sales Customizations

My Orders lists carrier tracking for every outgoing shipment. The order page uses Odoo's delivery list for the same links, the delivery PDF, the status, and the return slip.

Each shipped delivery with a tracking number is a link when the carrier has a URL, and plain text when it does not. Several numbers on one delivery are listed separately. An order with nothing shipped shows —. An order with some deliveries still open shows those links plus Partial. Cancelled shipments are skipped. The links are read from the order's pickings in one pass.
