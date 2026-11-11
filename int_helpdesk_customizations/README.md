# Help & Feedback

Help & Feedback is the site's helpdesk, open to everyone at `/help` (the old `/my/help` addresses redirect). The hub leads to five forms: a return, a warranty claim, website and operations feedback, a request for a part we do not stock, and general inquiries. Each submission becomes a private helpdesk ticket on an existing team, tagged for that kind. Returns and warranty claims use the returns team; feedback, part requests and general inquiries use the general inquiries team. Logged-in users are the ticket's customer and pick from their own orders. Guests type their name, email, phone and order number; helpdesk links the ticket to a contact by that email. A ticket copies the tags already on the customer's contact, with the same names. A contact tagged RVSB Dealer gets an RVSB Dealer tag on the ticket.

Each form in `HELP_KINDS` has a `retail` flag (logged-in non-dealers) and a `public` flag (guests). Set one to False to hide that form from that group. Guests are limited to 10 requests per hour per address (IP) and per email, and a hidden trap field turns away simple bots.

The header Help & Feedback button is the website-editor button, linked to `/help`. This module owns the My Portal tile, the hub, the forms, the tickets, the tags, and the staff alerts. It does not create a helpdesk team; a new request type is pointed at an existing team on every module update.

## Settings

Per company, under **Settings → Dealer Portal → Help & Feedback**:

- Returns, warranty, feedback, and part-request teams
- Return, warranty, feedback, and part-request tags

Each team dropdown is limited to that company and cannot create a team. Install and upgrade fill an empty team field by name: a team whose name contains "return" for returns and warranty, and a team whose name contains "inquir" or "general" for feedback and part requests. They also point the four kind tags at this module's tags and create the four alert lists. A team someone already chose is left alone. An empty team named exactly "Dealer Support" is archived. One that already has tickets is left in place, and new tickets are not assigned to it.

## Staff alerts

**Helpdesk → Configuration → Help & Feedback Alerts** (helpdesk managers). Each company has one row per kind. Tick internal users, add groups, and add extra inboxes. The mode can be an activity and an email, email only, or a To-Do activity only.

The email wording is the template **Help & Feedback staff alert**, under **Settings → Technical → Email Templates**. Recipients are filled in when the alert is sent, so editing the template does not change who receives it.

If a list has no one to notify, the sale order's salesperson is used when the ticket has an order. Otherwise the company email is used, and a warning is written to the log.

## Customer confirmation

Help & Feedback is only shown to a logged-in dealer. The ticket’s customer is that user, with their name and email taken from the account, so those forms do not ask for them. The public website forms still require a name and email, and a logged-in visitor sees those fields filled in.

Creating the ticket in **New** sends that stage's email template. General Inquiries and RVSB Returns share a New stage whose template is **Helpdesk: Ticket Received**. If a team's New stage has no template, this module sends **Help & Feedback received** to the email on the account instead. Edit that wording under **Settings → Technical → Email Templates**.

## Who sees the hub

An approved dealer is a contact whose commercial partner has a pricelist for the website company, and that pricelist is not the public user's pricelist (`base.public_user`) in the same company. The public user is never a dealer. A pending applicant stays on the public pricelist, so the hub stays hidden.

Internal users see the hub when every request type has a team, so staff can test it. If any of those teams is not set, the hub is hidden and a warning is logged. The page does not crash.

Returns only offer confirmed orders from the last 24 months for the dealer's commercial partner and the website company. A dealer with none of those orders sees "No orders found — use Feedback instead." A portal user can submit 10 of these tickets per hour.

## Decisions

- Kinds are helpdesk tags, not ticket types. This database has no `helpdesk.ticket.type` and no `ticket_type_id`.
- Tickets go to the existing teams. Returns and warranty claims go to RVSB Returns. Feedback and part requests go to General Inquiries. This module does not create a team.
- The ticket copies the contact's tags and uses the same names. It does not decide dealer or retail from the pricelist. Tickets with no customer are left untagged. Existing tickets are not backfilled.
- A second submit of the same request within a minute returns the ticket already created. The submit button also locks after the first click.
- Approved dealer means the pricelist check above. It is duplicated here and does not import the website customizations module.
- The work lives in `int_helpdesk_customizations`. No new module was added.
