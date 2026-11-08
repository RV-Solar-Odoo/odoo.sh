# Help & Feedback

Approved dealers open Help & Feedback from My Portal. The hub at `/my/help` leads to four forms: a return, a warranty claim, website and operations feedback, and a request for a part we do not stock. Each submission becomes a private helpdesk ticket on the company's Dealer Support team, tagged for that kind, with the dealer's contact as the customer so replies reach them.

The header link to `/my/help` is added by the website customizations. This module owns the My Portal tile, the hub, the forms, the tickets, the tags, the team, and the staff alerts.

## Settings

Per company, under **Settings → Dealer Portal → Help & Feedback**:

- Help & Feedback team
- Return, warranty, feedback, and part-request tags

The team dropdown is limited to that company. Install and upgrade fill an empty team with one named Dealer Support, point the four tag fields at this module's tags, and create the four alert lists. Later changes are left alone.

## Staff alerts

**Helpdesk → Configuration → Help & Feedback Alerts** (helpdesk managers). Each company has one row per kind. Tick internal users, add groups, and add extra inboxes. The mode can be an activity and an email, email only, or a To-Do activity only.

The email wording is the template **Help & Feedback staff alert**, under **Settings → Technical → Email Templates**. Recipients are filled in when the alert is sent, so editing the template does not change who receives it.

If a list has no one to notify, the sale order's salesperson is used when the ticket has an order. Otherwise the company email is used, and a warning is written to the log.

## Customer confirmation

This module does not send the customer a second email. The confirmation the dealer receives is the **Email Template** on the Dealer Support team's **New** stage (`helpdesk.stage.template_id`). Set that template by hand. Until it is set, the dealer still sees the confirmation page and can open the ticket at `/my/ticket/<id>`, but no stage email goes out.

## Who sees the hub

An approved dealer is a contact whose commercial partner has a pricelist for the website company, and that pricelist is not the public user's pricelist (`base.public_user`) in the same company. The public user is never a dealer. A pending applicant stays on the public pricelist, so the hub stays hidden.

Internal users see the hub when the company has a team, so staff can test it. If the team is not set, the hub is hidden and a warning is logged. The page does not crash.

Returns only offer confirmed orders from the last 24 months for the dealer's commercial partner and the website company. A dealer with none of those orders sees "No orders found — use Feedback instead." A portal user can submit 10 of these tickets per hour.

## Decisions

- Kinds are helpdesk tags, not ticket types. This database has no `helpdesk.ticket.type` and no `ticket_type_id`.
- Approved dealer means the pricelist check above. It is duplicated here and does not import the website customizations module.
- The work lives in `int_helpdesk_customizations`. No new module was added.
