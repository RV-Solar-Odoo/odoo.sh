# CRM Customizations

Dealer applications on the lead: tax exemption claims, the application's documents,
and Create Dealer Account.

## Documents tab (leads and opportunities)

- Files are grouped by label: Copy of Business License, Tax Exemption Certificate,
  Business Storefront + Interior, any labels staff add, then Other Attachments.
- Each file: **View** (Odoo's built-in viewer, the same one the chatter uses), **Download**,
  **Change Label**, **Copy to Contact** (reviewed files, once the lead has a contact), and
  **Delete** (sales managers and administrators, after a confirmation).
- **Reviewed** saves as soon as it is ticked and shows who and when. Ticking, unticking,
  uploads, label changes and deletes are logged in the chatter.
- **Upload Document** takes one or more files and a label. Pick an existing label or type a new one.
- Every document is a normal attachment on the lead, so it also shows in the chatter's Files.
  Deleting it there has the same rule: managers and administrators only.

Website form uploads are filed under the label that matches the form field's name
(`LABEL_ALIASES` in `models/lead_document.py`). A field with no matching label gets a new label of its own name.
The Tax Exemption Certificate, from the bound field or the custom "Exemption Certificate" upload,
is moved from `x_tax_exemption_document` onto the tab when the lead is created.

## Tax exemption

The Tax Exemption tab keeps Tax Exempt?, the reason, and Approved, plus a Certificate status
(Missing / Not reviewed yet / Reviewed). **Grant Tax Exemption** needs a reviewed certificate,
and copies it to the contact's Tax Exemption Certificate field.

## Create Dealer Account

Copies reviewed documents to the dealer's company contact (its Files), named
"Label – file name", once each. Unreviewed files are listed in the chatter note as skipped.

Sets the company contact's payment terms, Net 10th by default (`int_account_customizations.payment_term_net_10th`,
due the 10th of the month after the invoice). Clearing the field leaves the contact's terms as they are. With terms
and a credit limit, the dealer can use Place Order on Account at checkout (SPEC decision 37).

## Dealer application: address and social links

The website editor's field list for the dealer application (a Create an Opportunity form) now offers:

- **Business address**: the lead's own Street, Street2, City, ZIP and Country, plus **State / Province**, a text
  box matched to the state by code or name ("TX", "Texas"). Unmatched text stays on the lead's Application tab.
  The country defaults to the US when an address is given.
- **Billing Address Is Different** and the Billing Street, Street 2, City, State / Province, ZIP and Country
  fields. In the editor, set each billing field to be visible only when the box is set. Billing values are dropped
  if the box is unticked.
- **Facebook, Instagram, TikTok, LinkedIn** (optional boxes) and **Website**.

On the lead, billing and social links are on the **Application** tab. When the lead is converted, or Create
Dealer Account makes a new contact, the company gets the business address and the person sits under it; the
billing address becomes an **Invoice** address under the company. Linking an existing contact fills its address
only if it has none, and the lead keeps the address the dealer typed. Social links stay on the lead.

## My Portal → Documents (`/my/documents`)

A Documents tile for dealer logins (a dealer pricelist, see `_int_is_dealer_contact`). Every role can view
and download. Permissions come from the table in Contacts Customizations: `view_documents` (all roles),
`manage_certificates` (Owner, Accountant) and `manage_logo` (Owner). Files are served by
`/my/documents/file/<kind>/<id>` only when they belong to the logged-in dealer; anything else is a 404.
Uploads: PDF, JPG, PNG or BMP up to 20 MB, checked by extension and content.

- **Application Documents** are read live from the Documents tab of the dealer's leads (leads whose contact
  belongs to the dealer, for the website's company), grouped by the same labels. Nothing is copied.
  **Replace** adds a new, unreviewed document on the same lead under the same label (`int_replaces_id`),
  with a chatter note and a review activity for the lead's salesperson. The dealer then sees the new file
  with Pending Review; staff see both.
- **Certificates** (`int.dealer.certificate`): type (Resale, Sales Tax Exemption, Business License, Other),
  issuing state, number, issue and expiration dates, the file, and a status. Added or replaced from the
  portal, a certificate is Pending Review, with an activity for the dealer's salesperson (or the
  Certificate Reviewer in Settings). A replaced certificate stays valid until staff **Approve** the new
  one, then it becomes Replaced. **Reject** needs a note, which is emailed to the dealer's Owner and
  Accountant logins. Staff find them under CRM → Sales → Dealer Certificates and on the contact's
  Certificates button. Approving a tax or resale certificate for a tax-exempt contact also refreshes the
  contact's Tax Exemption Certificate file; exemption itself stays a staff decision.
- **Reminders** (daily job "Dealer Certificates: Reminders and Expiry"): an email at each threshold in
  Settings (60, 30 and 7 days by default), once each, then Expired the day after the expiration date,
  with an email to the dealer and an activity for staff. Ordering isn't blocked (SPEC decision 16).
- **Company Logo** is the company contact's image (`image_1920`). Use `image_512` or smaller for quotes.
  PNG, JPG or WebP up to 5 MB; no SVG.
- **Dealer Agreement** shows the newest file under the **Dealer Agreement** label on the dealer's leads,
  and "Not signed yet" until there is one. When the Sign template exists, filing the signed PDF under
  that label is all it needs.

## Settings and manual steps

- CRM → Settings → **Dealer Documents**: Certificate Reviewer and Certificate Reminders (per company).

- CRM → Configuration → **Document Labels** (sales managers): rename, reorder, or hide labels.
  The four starting labels keep working after a rename because the code finds them by `code`.
- The fiscal position "Wholesale — tax exempt" must exist for Grant Tax Exemption.

## Decisions made during build

- 2026-11-18: documents are `int.lead.document` rows that point at plain lead attachments.
  The Documents tab and Files therefore show the same files. See SPEC.md decision 36.
- 2026-11-18: files the website form posted before this update are filed as Other Attachments.
  Odoo did not record which upload field they came from. Certificates already approved are marked Reviewed.
- 2026-11-25: a pending replacement may sit beside the current certificate, so the limit is one current
  and one pending certificate per dealer, type and state (SPEC decision 40). Other is not limited.
- 2026-11-25: no backfill of certificate records for existing dealers. Their application files already
  show under Application Documents.
- 2026-11-27: Create Dealer Account on a lead with no contact now creates the company and the person, as
  converting the lead does, instead of one bare contact with only a name and email.
- 2026-11-27: State is a typed box, not Odoo's State field, which would list every state in the world.
