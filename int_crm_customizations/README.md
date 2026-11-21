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

## Settings and manual steps

- CRM → Configuration → **Document Labels** (sales managers): rename, reorder, or hide labels.
  The four starting labels keep working after a rename because the code finds them by `code`.
- The fiscal position "Wholesale — tax exempt" must exist for Grant Tax Exemption.

## Decisions made during build

- 2026-11-18: documents are `int.lead.document` rows that point at plain lead attachments.
  The Documents tab and Files therefore show the same files. See SPEC.md decision 36.
- 2026-11-18: files the website form posted before this update are filed as Other Attachments.
  Odoo did not record which upload field they came from. Certificates already approved are marked Reviewed.
