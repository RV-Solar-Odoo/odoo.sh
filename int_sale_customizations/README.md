# Sales Customizations

My Orders lists carrier tracking for every outgoing shipment. Deliveries, on My Portal, lists those same shipments, including ones still open and backorders. Open a row for the ship-to, the products, and the delivery slip. The order page links each shipment there. `/my/backorders` opens this list.

The order page uses Odoo's delivery list for the status and the return slip. Sale Information stays Sale Information.

Each shipped delivery with a tracking number is a link when the carrier has a URL, and plain text when it does not. Several numbers on one delivery are listed separately. An order with nothing shipped shows —. An order with some deliveries still open shows those links plus Partial. Cancelled shipments are skipped. The links are read from the order's pickings in one pass.

My Orders also searches by order number, PO, ship-to, product, or serial, and filters by date and status. All includes cancelled orders. Pins, reorder, export, and PO upload follow the portal role. A cancellation request does not cancel or refund the order. A sales manager confirms or denies it from the order. Store credit needs a program and a top-up product under Settings, and an accountant should review that before production.

## Decisions

Pins are per login, default limit 5, on the company (`int_max_pinned`). Reorder explains unavailable products before adding anything. A spreadsheet PO goes into the cart. A PDF PO becomes a draft quotation with a private attachment. The ship-to dock, forklift, and location type are copied onto the delivery when it is created.
