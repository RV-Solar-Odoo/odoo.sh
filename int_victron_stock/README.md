# Victron Stock

Shows our warehouse stock and Victron's E-Order stock on the shop, sells Victron's stock when ours runs out, and drafts a Victron RFQ for that shortfall. Victron's exact figure never reaches the browser; it shows as 20+ above 20.

## Backorders

A storable product with Odoo's **Sell when Out-of-Stock** ticked (Sales tab) can be ordered beyond what we and Victron have. The rest is a backorder. With the box unticked the old rule stays: "Currently unavailable" once both stocks are empty.

- **Shop.** The second stock line reads "Backorder · no ETA yet" when neither side has any. On the product page, Add to Cart asks first when part of the quantity would be backordered. The combination info only says yes or no (`int_backorder`), never Victron's count. Cart lines say what ships now, what ships within 7–10 days, and what is on backorder.
- **Split.** `sale.order._int_backorder_plan()` fills each line from our free stock, then Victron's, and the rest is backorder. At the payment step `_int_backorder_split()` moves that quantity to its own line (`int_backorder`, name ends "Backorder") at the same price. Opening the cart or checkout merges it back (`_int_backorder_merge()`).
- **Confirmation.** Backorder lines get their own delivery: a follow-up transfer of the ship-now delivery, or the whole delivery when nothing else is on it. They go on one shared draft **backorder PO** per vendor and company (`purchase.order.int_backorder_po`, Backorders filter). The vendor is the product's first vendor, otherwise Victron for products with a Victron SKU. The PO is assigned to the Victron buyer (Casey) with a "Review backorder PO" to-do. These POs are never the Victron shortfall RFQs. A product with no vendor gets a note on the sales order instead.
- **Invoicing and credit.** An open backorder line has nothing to invoice and no amount to invoice, so it is not billed and does not count against the dealer's credit. **Release Backorder for Invoicing** on the sales order makes it invoiceable whatever the product's invoicing policy. Staff add backorder shipping and invoice. Nothing is emailed automatically.
- **Payment.** `_get_prepayment_required_amount()` and `_is_paid()` leave open backorder lines out, so a payment for the rest confirms the order. Automatic invoicing then bills the paid lines, not a down payment.
- **Cancelling.** `_int_backorder_cancel()` cancels the lines' moves, sets them to 0, and takes them off a draft backorder PO. A confirmed PO gets a note to review. Cancelling the whole sales order does the same for its backorder lines.

## Manual checks before production

- Products on **Replenish on Order (MTO)** or with reordering rules would raise their own POs beside the backorder PO (DISCOVERY D17).
- Each backorderable product needs a vendor on its Purchase tab, or a Victron SKU, for the backorder PO.

## Decisions made during build

- "Sell when Out-of-Stock" is the backorder switch, so no new product setting was added. It is on by default for new products.
- Combo items are never split; they ship when the combo is complete.
- Backorder lines keep the price shown at checkout (`price_unit` is written back after the split), so a smaller quantity doesn't move them to another price break.
