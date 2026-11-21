# Accounting Customizations

Sales tax threshold emails, the credit card on My Portal, and dealer payment terms.

## Dealer payment terms

- **Net 10th** (`payment_term_net_10th`, noupdate): due the 10th of the month after the invoice date. Create Dealer Account sets it by default. Change a dealer's terms on the contact's Sales & Purchase tab.
- `res.partner._int_terms_status(company, amount, show_figures)` decides whether a customer can place an order on account. It needs all of these: terms other than Immediate, credit limits on for the company, a credit limit above 0, no overdue posted invoice, and available credit at least `amount`. Available credit is the limit less open receivables and confirmed, uninvoiced orders: the same figures as the My Portal credit card. Open backorders aren't counted because they have nothing to invoice until released. The reason text only shows the available amount when `show_figures` is set, for roles that can see credit.

## Decisions made during build

- An order over the available credit is paid by card. A temporary override is parked until after go-live (SPEC Section 11).
