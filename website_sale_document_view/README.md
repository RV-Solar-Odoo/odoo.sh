# eCommerce Product Documents: View in Browser (Odoo 19)

Out of the box, documents in the **Documents** block of an eCommerce product page
are served with `Content-Disposition: attachment`, so the browser always saves
them — even from "Open link in new tab". This module adds a **View** button that
opens PDFs (and images) in a new tab, and keeps **Download** next to it.

## What it changes

* `controllers/main.py` — extends the existing `/shop/<product>/document/<id>`
  route so `?download=0` serves PDFs and images inline. All of website_sale's access
  checks (published product, document shown on product page, etc.) still run;
  only the response header is rewritten.
* `views/templates.xml` — inherits `website_sale.product` and swaps each
  document link for a row with View / Download buttons. "View" appears only for
  PDFs and images; other file types get Download only. URL-type documents keep
  their "Open" link.

## Install

1. Copy this folder into your custom addons path (next to your other custom
   modules, e.g. `website_sale_tag_groups`).
2. Restart Odoo / redeploy (Odoo.sh: push to the branch).
3. Apps → Update Apps List → search "View in Browser" → Install.
4. Hard-refresh a product page that has documents.

## Optional: use Odoo's built-in pdf.js viewer instead

Android Chrome downloads PDFs even when served inline. If you want every visitor
to get an in-browser viewer with zoom / print / download, open
`views/templates.xml` and swap the `view_url` line for the commented
pdf.js alternative right below it. It is untested: check that `url_quote` is
available in the template first.

## Uninstall

Uninstalling restores the stock single-link behaviour; nothing is stored in the
database by this module.
