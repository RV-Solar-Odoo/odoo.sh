# Portal Customizations

My Portal shows the dealer's shipments, salesperson, and credit.

## What dealers see

- **My Orders** has a Tracking column. Each shipped delivery with a tracking number is a link when the carrier has a URL, and plain text when it does not. Several numbers on one delivery are listed separately. An order with nothing shipped shows —. An order with some deliveries still open shows those links plus Partial.
- The **order page** lists every outgoing shipment, shipped or not, with the same links.
- **Your sales rep** sits at the top of My Portal: name, email, phone, and photo. It uses the salesperson on the company contact, so an extra login sees the same person. The card is hidden when no salesperson is set.
- **Credit** sits beside it, and again at the top of Invoices. It shows the limit, the amount used, the amount left, and a bar. Green is under 75%, amber is 75% to 90%, red is over 90%. Over the limit, the available amount is zero and the card says how far over. The used amount is Odoo's open receivables plus confirmed orders that are not invoiced yet. A negative receivable is shown as credit on account and is not subtracted from the used amount.

## Who can see credit

Owner and Accountant. Buyer and Viewer get no credit figures. Internal users always can. The role is **Portal role** on the contact, under Sales. Existing contacts stay Owner.

The company switch **Sales Credit Limit** must be on, and the commercial partner's limit must be above zero. Otherwise the card is hidden.

## Store credit

An empty `div#rvsb_account_cards` sits beside the credit card for a later store-credit card.

## Decisions

- This is `int_portal_customizations`, not `rvsb_portal_account_info`.
- Phone uses `work_phone` when that field exists, otherwise phone, otherwise mobile.
- Tracking is read from the order's outgoing pickings in one pass. Cancelled pickings are skipped.
