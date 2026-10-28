# eCommerce Tag Groups (website_sale_tag_groups)

Odoo 19 module. Groups product tags into labeled filter sections on the /shop
sidebar instead of one flat "Tags" list.

## What it adds
- **Tag Groups** model (Website > eCommerce > Tag Groups). Each group has:
  - Display: Checkboxes or Dropdown
  - Collapsed by default (otherwise sections start open on desktop and
    mobile; a section with a selected tag is always open)
  - Sequence (drag to reorder)
- **Filter Group** field on Product Tags. Tags with no group are *not* shown
  in the shop filters by default. To get a generic "Tags" section for them,
  activate the view "Show Ungrouped Tags Section" (Settings > Technical >
  Views, with developer mode on).
- Shop sidebar (desktop + mobile offcanvas) renders one section per group.
- **Auto-clear stale filters**: moving to a category (or search) where a
  selected tag is not used by any product drops that tag from the URL and
  redirects, so the shopper never lands on an empty page with no filters.
- **Category scoping**: only tags carried by products in the current category
  (or search) are listed, so groups with no matching tags disappear and a
  category with no tagged products shows no tag filters at all. Selected
  tags/attributes/price are not applied to this scoping, so sibling tags stay
  visible once one is picked. (Stock Odoo lists every tag site-wide.)
- **Filter logic**: AND across groups, OR within a group.
  "12V" + "Marine" returns products that are 12V *and* marine.
  "12V" + "48V" (same group) returns products that are either.
  Stock Odoo ORs every tag together; this is overridden in
  `product.template._search_get_detail`.
- **Tags on the shop grid card**: each product's visible tags are shown as
  colored badges under the product name on /shop, reusing the same badge
  template (and the same tag `color`) as the product detail page. Toggling
  "Product Tags" off in Customize on the product page hides them in both
  places, since it's the same underlying view.

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
- controllers/main.py           category/search scoping + auto-clear stale tags
- views/templates.xml           shop sidebar (desktop + mobile) overrides,
                                 plus tag badges on the shop grid card
- views/*_views.xml             backend forms/lists/menu
- security/ir.model.access.csv
