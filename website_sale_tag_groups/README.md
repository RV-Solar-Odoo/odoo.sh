# eCommerce Tag Groups (website_sale_tag_groups)

Odoo 19 module. Groups product tags into labeled filter sections on the /shop
sidebar instead of one flat "Tags" list.

## What it adds
- **Tag Groups** model (Website > eCommerce > Tag Groups). Each group has:
  - Display: Checkboxes or Dropdown
  - Collapsed by default (desktop only; mobile matches stock Odoo and opens
    a section only when one of its tags is selected)
  - Sequence (drag to reorder)
- **Filter Group** field on Product Tags. Tags with no group fall into a
  generic "Tags" section at the bottom.
- Shop sidebar (desktop + mobile offcanvas) renders one section per group.
- **Filter logic**: AND across groups, OR within a group.
  "12V" + "Marine" returns products that are 12V *and* marine.
  "12V" + "48V" (same group) returns products that are either.
  Stock Odoo ORs every tag together; this is overridden in
  `product.template._search_get_detail`.

## Install
1. Drop the `website_sale_tag_groups` folder into your Odoo.sh repo's addons
   directory (or any path on `addons_path`) and push / restart.
2. Apps > Update Apps List > install "eCommerce Tag Groups".
3. Make sure the shop sidebar "Tags" filter option is enabled:
   /shop > Edit > Customize > Tags.

## Setup
1. Website > eCommerce > Tag Groups: create e.g. "Battery Voltage",
   "Use Case", "Brand".
2. Website > eCommerce > Product Tags: set the Filter Group on each tag
   (the list view supports multi-edit, and the Tag Group form has an inline
   tag editor).
3. Assign tags to products as usual (Product > Sales tab > Product Tags, or
   via import on `product_tag_ids`).

## Notes
- No JavaScript changes: inputs keep `name="tags"` so stock website_sale JS
  aggregates them into the `?tags=` URL parameter.
- Dropdown groups allow one selection per group.
- Tags still respect "Visible to customers" and website restrictions.

## Files
- models/product_tag_group.py   new model
- models/product_tag.py         group_id field on product.tag
- models/product_template.py    AND/OR filter override
- views/templates.xml           shop sidebar (desktop + mobile) overrides
- views/*_views.xml             backend forms/lists/menu
- security/ir.model.access.csv
