# Dealer Portal — Module Build Specification

**Project:** RV Solar & Battery dealer portal on Odoo 19 Enterprise (Odoo.sh)
**Owner:** Casey Shirts · **Builder:** in-house developer, using Claude Code
**Version:** 1.1 · November 6, 2026 (Casey's decisions on quotes, certificates, alert lists and forced logout applied)
**Go-live target:** all active modules in production by Friday, December 4, 2026

This document holds everything needed to build the dealer portal modules: architecture, conventions, a full spec for each module, how the modules interact, test plans, and ready-to-use Claude Code prompts. Keep it in the repository at `docs/dealer-portal/SPEC.md` and treat it as the source of truth. When a decision changes, update this file first, then the code.

---

## Contents

1. How to use this document with Claude Code
2. Discovery: facts to gather before writing code
3. Architecture and module map
4. Shared conventions (all modules)
5. Odoo 19 verification checklist
6. Module specs
   - 6.0 `rvsb_dealer_base`
   - 6.1 `rvsb_portal_fixes` (Tasks 2–5)
   - 6.2 `rvsb_portal_account_info` (Tasks 6–8)
   - 6.3 `rvsb_portal_orders` (Tasks 9–14)
   - 6.4 `rvsb_portal_addresses` (Tasks 15–16) + `rvsb_portal_addresses_shippo`
   - 6.5 `rvsb_portal_documents` (Tasks 17–18)
   - 6.6 `rvsb_dealer_onboarding` (Task 19)
   - 6.7 `rvsb_portal_roles` (Task 20)
   - 6.8 `rvsb_dealer_quotes` (Task 21)
   - 6.9 `rvsb_installer_locator` (Task 22)
7. Configuration-only task (Task 1: Stripe Link)
8. Cross-module interaction map
9. Testing strategy and full regression checklist
10. Decisions log (defaults in effect; confirm with Casey)
11. Parked work
12. Claude Code prompt library (one prompt per module)
13. Schedule reference

---

## 1. How to use this document with Claude Code

1. Copy `CLAUDE.md` (supplied alongside this file) to the repository root. Claude Code reads it automatically at the start of every session.
2. Put this file at `docs/dealer-portal/SPEC.md`.
3. Build **one module per Claude Code session**, in the order in Section 3. Start each session with that module's prompt from Section 12.
4. Use **plan mode first** (Shift+Tab in Claude Code, or ask "plan only, don't write code yet"). Have Claude read the spec section and the real Odoo 19 source files listed under "Touch points", then propose a file-by-file plan. Approve or correct the plan before any code is written.
5. Require Claude to **verify every Odoo template ID, controller method and field name against the actual Odoo 19 source** before inheriting it (Section 5). Names in this spec that are marked *(verify)* are best guesses from earlier Odoo versions.
6. Require tests with every module (Section 9). On Odoo.sh, push to a development branch so tests run automatically on each build.
7. When Claude makes a decision the spec does not cover, it must ask, or note it in the module's `README.md` under "Decisions made during build" and in Section 10 of this file.

Good prompt habits for this project:

- Point at the section: "Implement Section 6.3, Task 11 only." Small, scoped asks produce better Odoo code than "build the whole module".
- Paste the real error: full traceback from the Odoo.sh build log or the browser console, plus the steps to reproduce.
- Ask for the diff to be explained: "List every inherited template and xpath you added, and why each anchor is stable."
- Ask Claude to re-read Section 4 before finishing any module, then confirm each convention is met.

---

## 2. Discovery: facts to gather before writing code

Collect these on staging and record the answers in `docs/dealer-portal/DISCOVERY.md`. Several specs depend on them.

| # | Question | Where to look | Used by |
|---|---|---|---|
| D1 | Exact names of every pricelist that counts as a dealer tier | Sales → Products → Pricelists | base, fixes |
| D2 | How the "Become a Dealer" form works today: which page, which form, which model receives submissions (crm.lead, res.partner, mail message, other), and where attachments land | Website editor → form properties; recent submissions | fixes, documents, onboarding |
| D3 | Where the "Become a Dealer" button lives: website menu record, header template, portal home, or page snippet | Website → Configuration → Menus; page HTML | fixes |
| D4 | Company and website records for RV Solar & Battery vs. Nomadiq (multi-company is enabled on this database) | Settings → Companies; Website → Configuration → Websites | all |
| D5 | Name, version and vendor of the installed Shippo add-on, and the method that builds the address payload sent to Shippo | Apps; the add-on's source in the repo or vendor package | addresses_shippo |
| D6 | Other custom modules in the repo and anything they inherit in portal/website_sale (known: `website_sale_tag_groups`, the Victron E-Order stock module) | repo | all (avoid conflicts) |
| D7 | Theme in use and any customized portal templates | Website → theme; Settings → Technical → Views filtered by "portal" with `arch_fs` empty (DB-edited views) | fixes, account_info |
| D8 | Whether Accounting → Settings → "Sales Credit Limit" is on, and which partners have limits | Accounting settings | account_info |
| D9 | Installed or available apps: Helpdesk, Sign, eLearning, Blog, Loyalty, Resellers (partner directory) | Apps | various |
| D10 | Payment providers in use on the RV Solar website and whether saved cards are used | Website → Payment providers | orders (refunds) |
| D11 | How "Approved Dealer" is tracked today (tag, pricelist only, or both) | Contacts | base |

---

## 3. Architecture and module map

All modules live in one folder in the repository, for example `addons/rvsb/`, with each module in its own subfolder. Every module depends on `rvsb_dealer_base`, which holds the shared building blocks: who counts as a dealer, the portal role field and permission check, company settings, shared tile styles, and security groups.

```
rvsb_dealer_base
├── rvsb_portal_fixes            (Phase 1)
├── rvsb_portal_account_info     (Phase 2)
├── rvsb_portal_orders           (Phase 3)
├── rvsb_portal_addresses        (Phase 4)
│     └── rvsb_portal_addresses_shippo   (bridge, auto-installs when the Shippo add-on is present)
├── rvsb_portal_documents        (Phase 5)
├── rvsb_dealer_onboarding       (Phase 6; also depends on rvsb_portal_documents)
├── rvsb_portal_roles            (Phase 7; depends on every portal module above)
├── rvsb_dealer_quotes           (Phase 8)
└── rvsb_installer_locator       (Phase 8)
```

Build order: base → fixes → account_info → orders → addresses (+ shippo bridge) → documents → onboarding → roles → quotes → installer_locator.

**Why a base module.** Two concepts are used by nearly every module: "is this customer an approved dealer?" and "may this portal user do X?". Defining them once in `rvsb_dealer_base`, from day one, means:

- Every module checks permissions through one helper, so Phase 7 (roles) adds a management UI and record rules without retrofitting earlier modules.
- Until Phase 7 ships, every portal user defaults to the Owner role, so behavior is unchanged.

---

## 4. Shared conventions (all modules)

**Naming**
- Module technical names: `rvsb_<area>`. Python model names for new models: `rvsb.<thing>` (for example `rvsb.dealer.certificate`).
- New fields on existing models: prefix `rvsb_` (for example `res.partner.rvsb_address_category`).
- XML IDs: `<module>.<descriptive_name>`. Templates: `rvsb_<module>_<purpose>`.
- Routes: under `/my/...` for portal pages and `/rvsb/...` for JSON or download endpoints.

**Manifest**
- `version`: `19.0.1.0.0`, bumped on every change that alters data or views.
- `license`: `OPL-1` (or as Casey decides). `author`: RV Solar & Battery.
- Declare `assets` for CSS/JS under `web.assets_frontend`. No inline `<style>` in templates.

**Multi-company and multi-website**
- Multi-company is enabled on this database. Every setting is stored per company (`res.company` fields exposed through `res.config.settings`). Every new model holding business data has `company_id`, with the standard multi-company record rule.
- Portal pages resolve the company from `request.website.company_id`. Never hardcode a company, website, pricelist, team or user ID. Everything configurable goes in Settings → Website → Dealer Portal.

**Security**
- Portal controllers must only ever return data for the logged-in user's commercial partner (`request.env.user.partner_id.commercial_partner_id`). When `sudo()` is needed, apply it only after building a domain constrained to that commercial partner, and never pass user input straight into a domain without validation.
- Every portal route checks permissions with `rvsb_dealer_base`'s helper (Section 6.0) before rendering or acting.
- Every new model has an `ir.model.access.csv` entry for internal users, and portal access only where explicitly specified.
- File uploads: validate extension and MIME type, cap size at 20 MB per file, store as `ir.attachment` linked to the record, never as a public attachment.

**Front end**
- Inherit templates with xpaths anchored on stable attributes (`t-call`, `id`, named `t-set`, `hasclass(...)`), never on position or text. Re-check every xpath against the Odoo 19 source.
- Reuse the portal's own card and tile markup so new tiles match the existing My Portal tiles exactly. Base provides `rvsb_dealer_base.portal_tile`, a wrapper around the standard portal home entry.
- Mobile-first. Test at 375 px wide.
- All user-facing strings are translatable (`_()` in Python; plain text in QWeb is picked up automatically).

**Code quality**
- No changes to Odoo core or the Enterprise source. Everything is done by inheritance or configuration.
- No monkey-patching. Override methods with `super()`.
- Use `@api.model_create_multi` for `create` overrides; avoid N+1 queries in portal list pages (prefetch, use `read_group`/`_read_group` for counts).
- Each module ships `README.md` (what it does, settings, dependencies, decisions made during build) and `tests/`.
- Add a data migration (`migrations/19.0.x.y.z/post-migrate.py`) whenever a release changes stored data that already exists in production.

**Terminology**
- The customer account area is called **My Portal** in all user-facing text (formerly "My Account").

---

## 5. Odoo 19 verification checklist

APIs changed between Odoo 16 and 19. Before using any of these, Claude must grep the Odoo 19 source on the build (or the local source tree) and use the real name. Record findings in `docs/dealer-portal/DISCOVERY.md`.

| Item | What to verify |
|---|---|
| Portal home entries | Template used for My Portal home cards (earlier versions: `portal.portal_my_home` with `portal.portal_docs_entry`), its parameters (icon, title, text, url, placeholder_count, config_card) and how counters are computed (`_prepare_home_portal_values`) |
| Security page | Template and route for "Connection & Security" (earlier: `/my/security`, `portal.portal_my_security`), field names for old/new passwords |
| Password reset | `auth_signup` reset template and field names (`password`, `confirm_password`) |
| My Orders | Controller in `sale/controllers/portal.py`: `portal_my_orders`, `_prepare_sale_portal_rendering_values`, `_prepare_orders_domain`, `_get_sale_searchbar_sortings`, searchbar input/filter hooks; templates `sale.portal_my_orders`, `sale.portal_my_quotations` |
| Cart API | Odoo 19 refactored cart methods. Find the current method that adds a product and quantity to the website order (earlier: `sale.order._cart_update`) |
| Portal reorder | Website setting and route for reorder from portal |
| Addresses | Portal address book route/template and the checkout address form (Odoo 18 added a `/my/addresses` page); the controller methods that validate and write address fields |
| Users and groups | Field name for a user's groups (`groups_id` was renamed in recent versions; check `res.users`), and how groups are categorised (privileges vs. categories) |
| SQL constraints | Odoo 19 declaration style for constraints (`models.Constraint` vs `_sql_constraints`) |
| List views | `<list>` tag (renamed from `<tree>` in Odoo 18) |
| View modifiers | `invisible=`/`readonly=` Python expressions (no `attrs`) |
| Activity plans | `mail.activity.plan` model, its `res_model` field and how plans are launched in code |
| Loyalty eWallet | `loyalty.program` with `program_type='ewallet'`, `loyalty.card.points`, and the history model (`loyalty.history` in recent versions) for adding balance |
| Payment refunds | Refund wizard on `account.payment` / `payment.transaction` for providers that support refunds (Stripe) |
| Sign | `sign.template` / `sign.request` creation API and roles |
| Credit limit | `res.partner.credit_limit`, `use_partner_credit_limit`, `credit`, `credit_to_invoice`; company flag `account_use_credit_limit` |
| Delivery tracking | `stock.picking.carrier_tracking_ref`, `carrier_tracking_url` |
| eLearning | `slide.channel` visibility/enroll fields and the method to add members |
| Resellers | Partner directory module (`website_crm_partner_assign`), `res.partner.grade_id`, publication flag and route |
| Commercial fields | Whether `property_product_pricelist` and the new `rvsb_*` partner fields sync from the company to child contacts (`_commercial_fields`) |

---

## 6. Module specs

Each module spec follows the same layout: **Purpose · Depends · Settings · Data model · Behavior · Routes and templates · Backend UI · Security · Interactions · Edge cases · Tests · Acceptance (Casey's sign-off list)**.

---

### 6.0 `rvsb_dealer_base`

**Purpose.** Shared foundation: dealer status, portal roles and the permission check, company-level settings, shared tile markup and CSS, and the website-menu visibility control.

**Depends:** `base`, `portal`, `website`, `sale`, `product`.

**Settings (Settings → Website → Dealer Portal; stored on `res.company`)**

| Field | Type | Meaning |
|---|---|---|
| `rvsb_dealer_pricelist_ids` | m2m `product.pricelist` | Pricelists that count as dealer tiers (Discovery D1) |
| `rvsb_dealer_tag_id` | m2o `res.partner.category` | "Approved Dealer" tag. Created by data file if missing (noupdate) |

**Data model**

`res.partner` (new fields):

| Field | Type | Notes |
|---|---|---|
| `rvsb_is_approved_dealer` | Boolean, computed, stored, not synced to children directly | True when the **commercial partner** has the Approved Dealer tag OR its pricelist is in `rvsb_dealer_pricelist_ids` for the partner's company. Recompute on changes to `category_id`, `property_product_pricelist`, `parent_id` (depends through `commercial_partner_id`). Because the pricelist is company-dependent, compute in the context of the website's company; also expose a non-stored helper `_rvsb_is_dealer(company)` that always computes fresh |
| `rvsb_portal_role` | Selection: `owner`, `buyer`, `accountant`, `viewer`. Default `owner` | Role of this contact when it logs into the portal. Only meaningful on contacts that have a portal user. Not a commercial field |

`website.menu` (new field):

| Field | Type | Notes |
|---|---|---|
| `rvsb_visibility` | Selection: `all` (default), `non_dealers`, `dealers` | Inherit the menu rendering template so a menu is skipped when the condition fails for the current visitor. Public visitors count as non-dealers |

**Permission helper**

In `res.users` (or a mixin on `res.partner`), add:

```python
RVSB_PERMISSIONS = {
    'view_orders':        {'owner', 'buyer', 'accountant', 'viewer'},
    'place_orders':       {'owner', 'buyer'},
    'cancel_orders':      {'owner', 'buyer'},
    'pin_orders':         {'owner', 'buyer'},
    'upload_po':          {'owner', 'buyer'},
    'export_orders':      {'owner', 'buyer', 'accountant'},
    'manage_addresses':   {'owner', 'buyer'},
    'view_invoices':      {'owner', 'accountant'},
    'make_payments':      {'owner', 'accountant'},
    'view_credit':        {'owner', 'accountant'},
    'view_store_credit':  {'owner', 'accountant'},
    'manage_certificates':{'owner', 'accountant'},
    'export_pricing':     {'owner'},
    'view_resources':     {'owner', 'buyer', 'accountant', 'viewer'},
    'submit_tickets':     {'owner', 'buyer', 'accountant'},
    'create_quotes':      {'owner', 'buyer'},
    'manage_users':       {'owner'},
}

def rvsb_can(self, permission) -> bool
```

- Internal users always return True (staff testing as themselves).
- Public user returns False for everything.
- Portal users: look up `self.partner_id.rvsb_portal_role` (default `owner`) in the table.
- Add a controller helper `rvsb_require(permission)` that raises `werkzeug.exceptions.Forbidden` (or redirects to `/my` with a flash message) when the check fails. Every module's routes call it.
- In QWeb, templates call `request.env.user.rvsb_can('...')` to hide UI elements.
- Keep the table in one place; Phase 7 reads and extends it. If Casey changes the role matrix (Section 10), change it only here.

**Shared front end**
- `rvsb_dealer_base.portal_tile`: a QWeb template rendering one card identical to the standard My Portal home card, with params `icon`, `title`, `text`, `url`, and optional `badge`. Every module uses it for new tiles.
- `static/src/scss/rvsb_portal.scss`: shared styles (tile grid, status pills, credit bar colours, empty states).

**Alert lists (who gets notified)**

Casey's requirement: staff choose who receives each kind of alert by ticking people from a list of everyone in the company, and can add or remove people or whole groups at any time without code.

New model `rvsb.alert.list` (one record per alert type, per company):

| Field | Type | Notes |
|---|---|---|
| `name` | Char | e.g. "Cancellation requests" |
| `code` | Selection, unique per company | `cancel_request`, `help_return`, `help_warranty`, `help_feedback`, `help_part`, `cert_review`, `application_review`, `installer_listing` |
| `company_id` | m2o `res.company` | |
| `user_ids` | m2m `res.users`, domain internal users of the company | Shown with the `many2many_checkboxes` widget: every internal user listed with a tick box |
| `group_ids` | m2m `res.groups` | Optional: tick a whole group (e.g. "Sales / Administrator"); every member is included automatically, including people added to that group later |
| `extra_emails` | Char | Optional comma-separated addresses (shared inboxes such as orders@) |
| `notify_mode` | Selection: `activity_and_email` (default), `email_only`, `activity_only` | |
| `recipient_user_ids` | m2m computed (not stored) | `user_ids` ∪ users of `group_ids`, active and internal only |

- Data file creates the eight lists for each company (noupdate), empty. Settings → Website → Dealer Portal shows a "Notifications" block with one line per list ("Cancellation requests — 3 people, 1 group, orders@… → Edit") opening the list form.
- Menu: Sales → Configuration → Dealer Portal Alerts (list of all eight, editable by `group_rvsb_dealer_manager`).
- Helper `self.env['rvsb.alert.list']._rvsb_notify(code, record, summary, body, company)`: creates one To-Do activity per recipient user (deadline today) and/or sends one email to all recipients plus `extra_emails`, per `notify_mode`. Adds recipient users as followers of the record. Every module calls this helper; no module stores its own list of users.
- If a list resolves to nobody, fall back to the record's salesperson, then to the company's email, and log a warning.

**Security groups**
- `rvsb_dealer_base.group_rvsb_dealer_manager` ("Dealer Portal Manager", implies `base.group_user`): approves applications and cancel requests, reviews certificates, approves installer listings. Assign to sales management.

**Tests**
- Dealer flag: tag only, pricelist only, both, neither; child contact inherits from company; multi-company pricelist case.
- `rvsb_can` matrix: every permission × every role, plus internal and public users.
- Menu visibility for public, retail portal, dealer portal.
- Alert lists: recipients from ticked users plus group members (including a user added to the group later), archived/portal users excluded, extra emails included, fallback when empty, each notify mode.

**Acceptance**
- No visible change for users. Settings page shows the Dealer Portal section with the two fields.

---

### 6.1 `rvsb_portal_fixes` (Tasks 2–5)

**Purpose.** Password field fix, security-page rename, hide Become a Dealer for approved dealers, and the Help & Feedback hub.

**Depends:** `rvsb_dealer_base`, `auth_signup`, `portal`, `website`, `helpdesk`.

**Settings (per company)**

| Field | Type | Meaning |
|---|---|---|
| `rvsb_help_team_id` | m2o `helpdesk.team` | Superseded by decision 20. Use the existing teams, one per kind. Do not create "Dealer Support". |
| `rvsb_ticket_type_return_id` | m2o `helpdesk.ticket.type` | "Return" |
| `rvsb_ticket_type_warranty_id` | m2o `helpdesk.ticket.type` | "Warranty Claim" |
| `rvsb_ticket_type_feedback_id` | m2o `helpdesk.ticket.type` | "Feedback" |
| `rvsb_ticket_type_part_id` | m2o `helpdesk.ticket.type` | "Part Request" |

Data file (noupdate): create the four ticket types if they don't exist.

**Task 2 — Blank password fields**
- Inherit the reset-password template and the portal change-password template (Section 5).
- On new-password inputs: `autocomplete="new-password"`, `value=""`. On the current-password input: `autocomplete="current-password"`, `value=""`.
- Make sure no default value is rendered from `qcontext`.
- If the asterisks persist, check the browser devtools for an autofill extension and confirm the HTML `value` attribute is empty. Document the finding in the README.

**Task 3 — Rename**
- Change the home card title and the page heading from "Connection & Security" to "Password & Security". Use xpath on the title attribute/text node of the card and the `<h3>`/breadcrumb of the page; also update the breadcrumb.
- Check for the string in the theme's customized views (Discovery D7).

**Task 4 — Hide Become a Dealer**
- Depending on Discovery D3:
  - **Website menu:** set `rvsb_visibility = 'non_dealers'` on the menu record (data file or documented manual step; prefer a manual step documented in the README, since menu IDs differ per database).
  - **Template or snippet button:** wrap it in `t-if="not request.env.user.partner_id.rvsb_is_approved_dealer"`.
- Pending applicants (not yet approved) still see it.

**Task 5 — Help & Feedback**

*Entry point.* For approved dealers with the `submit_tickets` permission, show a "Help & Feedback" button in the same spot Become a Dealer used (menu with `rvsb_visibility = 'dealers'`, or the same template slot) and a "Help & Feedback" tile on My Portal home.

*Hub page.* `GET /my/help`, title "Help & Feedback". Four tiles using `rvsb_dealer_base.portal_tile`, the same size and shape as the My Portal tiles, each with a title and a 1–2 line description of what the option does. Starter copy (Casey approves on staging):

| Tile | Description |
|---|---|
| Start a return | Return unused or incorrect items from an order. We'll review it and send return instructions. |
| Start a warranty claim | Report a product that has failed. Include the serial number and photos so we can process it quickly. |
| Website & operations feedback | Something broken, confusing or slow — on the site, in shipping, billing or anything else? Tell us and we'll fix it. |
| Request a part we don't stock | Need something we don't carry? Tell us what it is and roughly how many you use per year. |

*Forms.* `GET/POST /my/help/<kind>` where kind ∈ `return`, `warranty`, `feedback`, `part`. Built as module templates posting to the module's own controller (not the website form builder), so fields, validation and prefill stay in code.

| Kind | Fields (required marked *) |
|---|---|
| return | Order* (dropdown of the dealer's confirmed orders, last 24 months), product/SKU* (dropdown filtered to the chosen order's lines, populated via JSON route), serial number, quantity*, reason* (select: wrong item, damaged in shipping, ordered in error, other), details, photos (up to 5 images) |
| warranty | Order (dropdown, optional), product/SKU* (text or dropdown), serial number*, install date*, description of failure*, photos/video (up to 5 files, images or mp4/mov) |
| feedback | Area* (select: website, ordering, shipping, billing, other), description*, screenshot (up to 3 images) |
| part | Manufacturer*, part number or description*, estimated quantity per year, link |

*On submit.* Create `helpdesk.ticket` with:
- `team_id` = setting; `ticket_type_id` = setting for the kind;
- `partner_id` = the logged-in contact (so replies go to the person who asked); `partner_email` from the user;
- `name`: "[Return] SO1234 – Victron MultiPlus-II 12/3000" (pattern `[<Kind>] <order or area> – <product or short text>`);
- `description`: an HTML summary of all fields;
- attachments linked to the ticket;
- for return/warranty with an order, also post a note on the `sale.order` linking the ticket;
- notify the matching alert list (`help_return`, `help_warranty`, `help_feedback`, `help_part`) via `_rvsb_notify`; its users are added as ticket followers. If the list has exactly one user, also set them as the ticket's assignee; otherwise leave assignment to Helpdesk's team rules.

Then show a confirmation page with the ticket reference and a link to the ticket in the portal (Helpdesk provides `/my/tickets`). The confirmation email comes from Helpdesk's stage template on the "New" stage; document that configuration in the README.

*Validation.* Server-side checks for required fields, order ownership (the order must belong to the commercial partner), file type/size, and a CSRF token. Rate-limit to 10 tickets per user per hour.

**Security.** Routes require login plus `submit_tickets`. The order and product dropdown JSON route returns only the commercial partner's orders.

**Interactions.** The dealer flag comes from base (Phase 6 approval sets the tag, which flips the button). Phase 7 roles hide the hub for Viewers.

**Edge cases.** A dealer with zero orders: the Return form shows "No orders found — use Feedback instead". The helpdesk team is not configured: hide the hub and log a warning.

**Tests.** Password templates render empty values; rename present in both places; button visibility for retail/pending/approved; each form creates the correct ticket type and team; rejects an order belonging to another partner; attachment limits.

**Acceptance.** As listed in the Kickoff Guide, Tasks 2–5.

---

### 6.2 `rvsb_portal_account_info` (Tasks 6–8)

**Purpose.** Tracking links in My Orders, assigned sales rep, and credit limit/usage on My Portal.

**Depends:** `rvsb_dealer_base`, `sale_stock`, `stock_delivery` (verify name; earlier `delivery`), `account`.

**Task 6 — Tracking column**
- Add a "Tracking" column to the My Orders list (and the order detail page header).
- For each order: outgoing pickings (`picking_ids` filtered to `picking_type_code == 'outgoing'`, state `done`) that have `carrier_tracking_ref`. Render one link per picking: text = tracking number, href = `carrier_tracking_url` (open in new tab, `rel="noopener"`). If the URL is empty, show the number as plain text.
- An order with tracking refs separated by commas in one picking: split and render each.
- Unshipped: "—". Partially shipped: links for shipped pickings plus a "Partial" pill.
- Performance: compute in one pass over the page's orders with prefetching. No per-row queries.

**Task 7 — Sales rep card**
- Source: `commercial_partner_id.user_id` (salesperson on the company contact).
- Card on My Portal home (top of page, above the tiles): "Your sales rep", name, email (`mailto:`), phone (`tel:`), from the user's related partner (`work_phone`/`phone`, `email`). Avatar if available.
- Hidden when no salesperson is set.

**Task 8 — Credit card**
- Visible when the company has credit limits enabled AND the commercial partner has a limit > 0 AND the user has `view_credit`.
- Values (company currency, computed with sudo on the commercial partner only):
  - **Limit** = `credit_limit` (respecting `use_partner_credit_limit` and the company default; verify how Odoo 19 resolves the effective limit)
  - **Used** = `credit` (open receivable balance) + `credit_to_invoice` (confirmed, not-yet-invoiced order amounts)
  - **Available** = max(limit − used, 0); if used > limit, show "Over limit by $X" in red
  - **Usage %** = used / limit
- Display: three dollar figures plus a horizontal bar. Colors: green below 75%, amber 75–90%, red above 90%. Caption: "Includes open invoices and confirmed orders not yet invoiced. Updated in real time."
- Placement: My Portal home, next to the sales rep card; also at the top of the invoices page.

**Security.** All values computed server-side for the user's own commercial partner. No new routes.

**Interactions.** Phase 3 adds store credit display beside the credit card (orders module renders it into a slot this module provides: an empty `<div id="rvsb_account_cards"/>` container with a `t-call` hook other modules can xpath into). Phase 7 hides the credit card for Buyers and Viewers.

**Edge cases.** Multi-currency: if the partner trades in another currency, show the company-currency figures and a note. Negative receivable (customer has credit): treat as 0 used plus a "Credit on account: $X" line.

**Tests.** Tracking: none, one, multiple pickings, missing URL. Rep: set and unset. Credit: under, near and over the limit; no limit; limits disabled; values match the backend partner form to the cent.

---

### 6.3 `rvsb_portal_orders` (Tasks 9–14)

**Purpose.** Make My Orders usable at hundreds of orders: search and filters, backorders, cancellation requests with store-credit refunds, pinned orders, export, PO upload.

**Depends:** `rvsb_dealer_base`, `rvsb_portal_account_info`, `sale_stock`, `website_sale`, `sale_loyalty`, `account_payment`, `payment`.

**Settings (per company)**

| Field | Type | Meaning |
|---|---|---|
| `rvsb_store_credit_program_id` | m2o `loyalty.program` (domain `program_type = 'ewallet'`) | The "Store Credit" eWallet program |
| `rvsb_store_credit_product_id` | m2o `product.product` | Product used for store-credit top-up invoices (the eWallet program's top-up product) |
| `rvsb_max_pinned` | Integer, default 5 | Pin limit |

**Task 9 — Search and filters**
- Extend the My Orders controller's search inputs (verify hook names, Section 5). Searchbar options:

| Search in | Domain (always ANDed with the portal's own partner domain) |
|---|---|
| Order # | `name ilike` |
| PO # | `client_order_ref ilike` |
| Ship-to | `partner_shipping_id.name`, `.street`, `.city`, `.zip` ilike (OR) |
| Product / SKU | `order_line.product_id.default_code` or `.name` ilike |
| Serial # | `picking_ids.move_line_ids.lot_id.name` ilike |
| All | OR of the above |

- Date range: `date_from`/`date_to` inputs filtering `date_order`.
- Status filter: All, Open (not fully delivered), Shipped, Backordered, Cancelled, Cancellation requested.
- Sort: newest (default), oldest, order #, total.
- Keep search/filter in the query string so paging and export keep them.
- Serial search: run the lot search with sudo, restricted to pickings whose `sale_id.partner_id` is a child of the commercial partner, then filter orders by the resulting IDs. Never expose lots belonging to another customer.
- Performance target: under 2 seconds on 300+ orders. Add database indexes only if profiling shows the need (`index=True` on new fields only).

**Task 10 — Backorders**
- New page `GET /my/backorders` and a tile "Backorders" with a count badge; also a "Backordered" filter in My Orders.
- Rows: one per open backordered line. Source: outgoing pickings not done/cancelled whose `backorder_id` is set (or, more generally, open outgoing pickings for orders where some delivery is already done), and their `move_ids` with remaining quantity.
- Columns: product (SKU + name), quantity outstanding, original order (link), PO #, expected date (`picking.scheduled_date`, or `date_deadline` if set), status pill.
- Empty state: "No backorders. Everything you've ordered has shipped."

**Task 11 — Cancellation requests and store credit**

*New fields on `sale.order`:*

| Field | Type |
|---|---|
| `rvsb_cancel_state` | Selection: `none` (default), `requested`, `approved`, `denied` (tracked) |
| `rvsb_cancel_reason` | Selection: `no_longer_needed`, `ordered_wrong_item`, `found_elsewhere`, `delay`, `other` |
| `rvsb_cancel_note` | Text (dealer's note) |
| `rvsb_cancel_refund_pref` | Selection: `store_credit`, `original` |
| `rvsb_cancel_requested_by` | m2o `res.users` |
| `rvsb_cancel_requested_on` | Datetime |
| `rvsb_cancel_decided_by` | m2o `res.users` |
| `rvsb_cancel_decision_note` | Text |
| `rvsb_can_request_cancel` | Boolean, computed (not stored) |

*Eligibility (`rvsb_can_request_cancel`):* state is `sale` (or `sent` if paid online), no outgoing picking is `done`, no outgoing picking is in a "packed/ready and labels printed" state if that is detectable (otherwise ignore), `rvsb_cancel_state` in (`none`, `denied`), and the user has `cancel_orders`.

*Dealer flow (portal):*
1. "Request cancellation" button on the order detail page and in the row's action menu.
2. Modal or page: reason (required), note, refund preference radios — **Store credit** (listed first, with helper text "Applied instantly to your next order once approved") and **Original payment method**. If the order is unpaid (credit terms or not yet paid), hide the refund choice.
3. Submit sets `rvsb_cancel_state = 'requested'` plus the request fields, posts a chatter message, and shows the order with a "Cancellation requested — we'll confirm shortly" pill. **Nothing is cancelled and nothing is refunded at this point.**

*Staff alert:* call `_rvsb_notify('cancel_request', order, ...)` (base alert lists); the order's salesperson is always added as well. The email subject is "Cancel request: SO1234 – <Dealer>" and the body includes order status, picking states and payment status.

*Backend:* on the sale order form, a banner when `rvsb_cancel_state = 'requested'` with buttons **Confirm cancellation** and **Deny** (visible to `group_rvsb_dealer_manager` and sales managers). A filter "Cancellation requested" in the Sales order list view.

*Confirm cancellation (server action):*
1. Re-check that no outgoing picking is done. If one is, block with a message.
2. Cancel the order using the internal cancel method (Odoo's `_action_cancel`, verify), which cancels open pickings.
3. Handle money:
   - **Not paid, not invoiced:** nothing further.
   - **Invoiced, not paid:** create and post a full credit note (reversal) for the open invoice(s) and reconcile it with the invoice.
   - **Paid, refund to original:** create and post a credit note; then refund the payment through the provider's refund flow (Stripe supports refunds through Odoo's payment refund wizard; verify the API). If the payment was not made through a refundable provider (check, bank transfer), create an activity for accounting to refund manually.
   - **Paid, refund as store credit:** create and post a credit note. Then create and post an invoice for the store-credit top-up product for the same amount and reconcile it against the credit note (receivable nets to zero; the liability moves to the eWallet product's income/liability account). Then add the amount to the partner's eWallet card in the Store Credit program (create the `loyalty.card` for the commercial partner if none exists) and record a history line "Refund – SO1234". **Have the accounting setup reviewed by Casey's accountant before go-live; see Section 10.**
   - Staff can override the dealer's refund preference with a selection on the confirm wizard.
4. Set `rvsb_cancel_state = 'approved'`, the decision fields, and post to chatter.
5. Email the dealer (template `rvsb_portal_orders.mail_cancel_approved`) with the refund method and amount.

*Deny:* wizard with a required note. Sets `denied`, emails the dealer (template `mail_cancel_denied`) with the note, closes the activities. The order continues normally. The dealer may request again later (state `denied` allows it).

*Store credit display:* a "Store credit" card in the `rvsb_account_cards` slot showing the eWallet balance (users with `view_store_credit`). The eWallet must be configured to be usable at checkout (sale_loyalty handles application at checkout).

*Shipping race condition:* if staff start picking an order with a pending cancel request, show a warning banner on the picking ("Cancellation requested by customer") so the warehouse holds it. Add a related field on `stock.picking` for this.

**Task 12 — Pinned orders**
- Pins are per user: `res.users.rvsb_pinned_order_ids` (m2m `sale.order`), max `rvsb_max_pinned` (default 5).
- Pin/unpin icon on each row and on the order page (JSON route `POST /rvsb/orders/<id>/pin`, checks ownership and `pin_orders`). A 6th pin returns a message: "You can pin up to 5 orders. Unpin one first."
- Pinned orders appear in a "Pinned" section at the top of My Orders, above search results, unaffected by filters.
- "Reorder" button on pinned rows and the order page: use Odoo's built-in portal reorder (enable the website setting; verify route). If not available in Odoo 19, add each line to the cart at current price through the current cart API, skip unavailable or unpublished products, and show a notice listing skipped items.

**Task 13 — Export**
- Route `GET /rvsb/export/orders?format=xlsx|csv&<current filters>`; route `GET /rvsb/export/addresses?format=xlsx|csv`.
- Orders export: one row per order line. Columns: Order #, Order date, PO #, Status, Ship-to name, Ship-to address (one cell), SKU, Product, Qty ordered, Qty delivered, Unit price, Line subtotal, Order total, Tracking #s, Serial #s (comma-separated, from done move lines for that product).
- Addresses export: Name, Category (business/customer), Commercial/Residential, Dock, Forklift, Street, Street 2, City, State, ZIP, Country, Phone, Email.
- XLSX via `xlsxwriter` (bundled with Odoo); CSV UTF-8 with BOM so Excel opens it correctly. Filename `orders_<YYYY-MM-DD>.xlsx`.
- Applies the same domain and filters as the list. Cap at 10,000 rows with a message if exceeded.
- Permissions: `export_orders`; addresses export requires `manage_addresses`.

**Task 14 — Upload a PO**
- Page `GET /my/po-upload` (tile "Upload a PO", also a button on My Orders). Requires `upload_po`.
- Downloadable template `GET /rvsb/po-template.xlsx` with columns: `SKU`, `Qty`, and an optional header cell for `PO Number`.
- **XLSX upload:** parse with `openpyxl` (bundled; verify). Match SKU to `product.product.default_code`, restricted to products that are `sale_ok`, published on the current website, and allowed for the company. Add matched lines to the current website cart (current cart API), set `client_order_ref` from the PO number if given. Show a results page: lines added, and lines rejected with a reason (unknown SKU, not available, qty not a positive integer). Then link to the cart.
- **PDF upload:** create a draft quotation (`sale.order`, state draft) for the commercial partner, with the user as contact, `client_order_ref` from an optional PO number input, the PDF attached and posted in chatter, and an activity for the salesperson "Enter PO from upload". Show confirmation: "We've received your PO and will send a quote shortly."
- Limits: 10 MB, 500 rows.

**Security.** Every route checks ownership and the matching permission. Export streams only the user's data.

**Interactions.** Uses account_info's card slot. Phase 7 hides buttons by role. Phase 4's address fields appear in the export.

**Edge cases.** Order with multiple invoices; partially paid invoices (refund only the paid portion; credit-note the rest); a cancel request on an order that ships before staff act (confirm blocks); dealer leaves the company (pins belong to the user, so they leave with them); products archived since the original order (reorder skips them).

**Tests.** Every search field; serial isolation between customers; backorder list after a partial delivery; cancel flows: unpaid, invoiced-unpaid, paid→card (Stripe test mode), paid→store credit (balance increases, accounting nets to zero), deny, ship-before-confirm; pin limit; export columns and filters; PO upload valid/invalid SKUs, PDF path.

---

### 6.4 `rvsb_portal_addresses` (Tasks 15–16) and `rvsb_portal_addresses_shippo`

**Purpose.** Split the address book into business vs. customer (drop-ship) addresses, and record delivery-site details for accurate shipping.

**Depends:** `rvsb_dealer_base`, `website_sale`, `portal`, `stock_delivery` (verify).

**Data model — `res.partner` (address contacts):**

| Field | Type | Notes |
|---|---|---|
| `rvsb_address_category` | Selection: `business`, `customer`. Default `business` | Business location vs. customer/drop-ship |
| `rvsb_location_type` | Selection: `commercial`, `residential` | Required on new addresses created through the portal or checkout |
| `rvsb_has_loading_dock` | Boolean | Shown only when commercial |
| `rvsb_has_forklift` | Boolean | Shown only when commercial |

None of these are commercial fields; they belong to each address.

**Migration (post-install):** existing child addresses of dealer companies get `rvsb_address_category = 'business'` (Decision 4) and an empty location type (the dealer is prompted to set it the next time the address is used at checkout).

**Task 15 — Split address book**
- Portal address page (verify route, Section 5): two sections, "My business locations" and "Customer / drop-ship addresses", each with its own search box (name, street, city, ZIP) and paging (20 per page). The counts appear in the section headers.
- Each address card: name, address, category badge, location type, dock/forklift icons, Edit, "Move to business/customer" action.
- The add/edit address form gets a "This address is: My business location / A customer (drop-ship)" radio.
- Checkout address selection: show both groups under headings, business first; the search box filters both. Selecting a customer address works exactly like any delivery address.
- Requires `manage_addresses` to add, edit or move; Viewers and Accountants see read-only.

**Task 16 — Delivery details**
- Add to the portal and checkout address forms: "Commercial / Residential" (required radio) and, when commercial, checkboxes "Loading dock" and "Forklift on site" (toggled in JS; validated server-side: cleared if residential).
- On `sale.order`: related, read-only fields `rvsb_ship_location_type`, `rvsb_ship_has_dock`, `rvsb_ship_has_forklift` from `partner_shipping_id`, shown on the order form and in the checkout review step ("Commercial · Loading dock · Forklift").
- On `stock.picking`: snapshot (stored, copied at picking creation from the order's shipping address) of the same three fields, shown on the delivery form near the carrier fields and printed on the picking slip, so warehouse staff see "Residential — liftgate required" or "Commercial — dock, forklift" when quoting freight.
- Liftgate logic note on the picking: `liftgate_needed = residential OR (commercial AND NOT dock AND NOT forklift)`, as a computed boolean with a red badge.

**Bridge module `rvsb_portal_addresses_shippo`**
- `auto_install: True`, depends on `rvsb_portal_addresses` and the Shippo add-on (Discovery D5).
- Override the add-on's address payload builder so the "to" address includes Shippo's residential flag (`is_residential`) from `rvsb_location_type` (residential → True, commercial → False, unset → omit).
- If the add-on exposes no clean hook, override the narrowest method that builds the address dict and call `super()`. Document the method in the README.
- Test with a mocked Shippo request: assert the payload flag.

**Interactions.** The orders export includes these fields. The quote tool (Phase 8) can pick a customer address as the quote recipient. Blind shipping (parked) would later hang off customer addresses.

**Edge cases.** The billing/company address itself is always business and cannot be moved. Addresses created by staff in the backend default to business with no location type; checkout prompts for it.

**Tests.** Category default and move; search in each section; required location type at checkout; dock/forklift cleared when residential; picking snapshot; Shippo payload flag.

---

### 6.5 `rvsb_portal_documents` (Tasks 17–18)

**Purpose.** A Documents tab (application files, tax certificates with expirations and reminders, pricing download) and a dealer-only Resources tab.

**Depends:** `rvsb_dealer_base`, `website_sale`, `website_blog`, `website_slides`, `mail`.

**Settings (per company)**

| Field | Type | Default |
|---|---|---|
| `rvsb_cert_reminder_days` | Char | `60,30,7` |
| `rvsb_dealer_blog_id` | m2o `blog.blog` | "Dealer Bulletins" |
| `rvsb_dealer_channel_ids` | m2m `slide.channel` | Dealer training courses |

**New model `rvsb.dealer.certificate`**

| Field | Type | Notes |
|---|---|---|
| `partner_id` | m2o `res.partner`, required | Commercial partner |
| `company_id` | m2o `res.company` | Selling company |
| `cert_type` | Selection: `resale`, `sales_tax_exemption`, `other` | |
| `state_id` | m2o `res.country.state` | Issuing state |
| `cert_number` | Char | |
| `issue_date`, `expiration_date` | Date | Expiration optional (some certificates don't expire) |
| `attachment_id` | m2o `ir.attachment`, required | The file |
| `status` | Selection: `pending_review`, `valid`, `expiring` (≤ first reminder window), `expired`, `superseded`, `rejected` | Computed/stored and updated by cron |
| `replaced_by_id` / `replaces_id` | m2o self | Version history |
| `reviewed_by`, `reviewed_on` | m2o users, Datetime | |
| `reminder_sent_days` | Char | Thresholds already sent, e.g. `60,30`, to avoid duplicates |

Constraint: one active (`pending_review`/`valid`/`expiring`) certificate per partner + cert_type + state.

`res.partner` computed: `rvsb_cert_status` (worst status across active certificates) shown as a badge on the contact form and in the dealer list view.

**Task 17 — Documents tab**

Page `GET /my/documents` (tile "Documents"). Sections:

1. **Application documents.** Read-only list of attachments on the commercial partner flagged `rvsb_portal_category = 'application'` (new Selection field on `ir.attachment`, or a dedicated link model if adding a field to attachments is undesirable). Each has a view/download link through a module route that checks ownership (do not make attachments public). Phase 6 tags application files with this category on approval; for existing dealers, document a one-time backfill from wherever applications land today (Discovery D2).
2. **Tax & resale certificates.** Table: type, state, number, expiration, status pill, file link. Actions (permission `manage_certificates`): **Replace** (upload new file + number + expiration; creates a new record in `pending_review` that `replaces_id` the old one; the old one stays `valid` until staff approve the new one, then becomes `superseded`) and **Add certificate**. Staff review: `_rvsb_notify('cert_review', ...)` (base alert lists), with Approve/Reject buttons on the certificate form (Reject requires a note emailed to the dealer).
3. **Pricing.** Button "Download my pricing (XLSX)" (permission `export_pricing`). Columns: SKU, product name, category, the dealer's price (from their pricelist via the pricelist pricing method for qty 1; verify method name), MSRP if the MSRP pricelist is configured (Phase 8 setting; omit the column otherwise), stock status (in stock / ships in 5–7 days / backorder — reuse the Victron E-Order stock module's status if available, Discovery D6). Published, `sale_ok` products for the website only. Filename `pricing_<company>_<YYYY-MM-DD>.xlsx`.

**Reminder cron** (daily, 06:00 company time):
- For each active certificate with an expiration date: when days remaining ≤ a threshold not yet in `reminder_sent_days`, email the dealer (all contacts with `owner` or `accountant` role, else the company email) using template `mail_cert_expiring` ("Your <state> resale certificate expires on <date>. Upload a new one in My Portal → Documents."), notify the `cert_review` alert list, and record the threshold.
- On the day after expiration: status `expired`, email `mail_cert_expired`, activity for staff. Do not block ordering (Decision log); staff decide on tax treatment.

**Task 18 — Dealer Resources tab**

Page `GET /my/resources` (tile "Dealer Resources", permission `view_resources`, dealers only). Sections:
- **Announcements & technical bulletins:** latest 10 posts from `rvsb_dealer_blog_id`, with "View all" linking to the blog. Use blog tags "Announcement" and "Technical Bulletin" as section filters.
- **Training:** cards for each channel in `rvsb_dealer_channel_ids` with progress if enrolled.

Dealer-only enforcement:
- `blog.blog.rvsb_dealer_only` Boolean. For such blogs, override the blog controllers so non-dealers (public, retail portal) get a 404 on the blog, its posts, tags and feeds. Exclude them from the sitemap and set `noindex`. Add a record rule for portal/public on `blog.post` where `blog_id.rvsb_dealer_only = False` unless the user is a dealer (the rule domain can test `user.partner_id.rvsb_is_approved_dealer`). Remember that controllers often use `sudo()`, so the controller check is the main guard; the rule is a backstop.
- eLearning channels: set visibility to members only and enrollment to invite only (configuration). Auto-enroll the commercial partner's portal users when they become approved dealers (hook called by Phase 6 approval and a manual "Enroll all dealers" button in settings for existing dealers).

**Interactions.** Phase 6 approval tags application documents and enrolls the dealer in training. Phase 7 role checks for certificates and pricing. Phase 8 quote tool reuses the MSRP pricelist setting.

**Tests.** Certificate lifecycle (add → review → valid → expiring reminders at each threshold once → expired); replace keeps the old one valid until approved; documents of another partner return 404; pricing XLSX matches pricelist computation; dealer-only blog 404 for retail and public, accessible to dealers; sitemap exclusion.

---

### 6.6 `rvsb_dealer_onboarding` (Task 19)

**Purpose.** Replace the "move them to a new price tier" process with a tracked application: applicants get a real portal login immediately, staff work a checklist, approval sets everything in one step.

**Depends:** `rvsb_dealer_base`, `rvsb_portal_fixes`, `rvsb_portal_documents`, `website`, `portal`, `auth_signup`, `sign`, `mail`, `website_slides`.

**Settings (per company)**

| Field | Type | Meaning |
|---|---|---|
| `rvsb_application_plan_id` | m2o `mail.activity.plan` (res_model `rvsb.dealer.application`) | "Dealer Approval" plan |
| `rvsb_agreement_template_id` | m2o `sign.template` | Dealer agreement (placeholder on staging; final from Casey by Nov 30) |
| `rvsb_default_dealer_pricelist_id` | m2o `product.pricelist` | Pre-filled on the approve wizard |
| (alert list `application_review`) | base | Notified on new applications and info uploads; the plan's activities are assigned to these users unless the plan sets its own assignees |

**New model `rvsb.dealer.application`** (`mail.thread`, `mail.activity.mixin`)

| Field | Type | Notes |
|---|---|---|
| `name` | Char, sequence `DA/00001` | |
| `partner_id` | m2o `res.partner` | The applicant **company** (created on submit, `is_company=True`) |
| `contact_id` | m2o `res.partner` | The person applying (child of `partner_id`) |
| `user_id` | m2o `res.users` | The portal user created on submit |
| `company_id` | m2o `res.company` | From the website |
| Business fields | | Copy the current form fields exactly (Discovery D2): legal business name, DBA, EIN, business type, years in business, website, phone, address, resale/tax certificate number and state, business license number, expected monthly volume, how they heard about us, notes |
| `attachment_ids` | m2m `ir.attachment` | Uploaded documents (certificate, license, other) |
| `stage` | Selection: `received`, `under_review`, `info_requested`, `approved`, `rejected` (tracked) | |
| `portal_status` | Computed: `received` → "Received", `under_review`/`info_requested` → "Under review", `approved` → "Approved", `rejected` → "Not approved" | What the dealer sees |
| `checklist_done` | Boolean, computed | True when no plan activities remain open and the sign request is completed |
| `sign_request_id` | m2o `sign.request` | |
| `approved_by`, `approved_on` | | |
| `pricelist_id`, `credit_limit`, `salesperson_id` | Set at approval | |
| `rejection_reason` | Text | |

**Applicant flow (website)**
1. Replace or extend the current Become a Dealer form (Discovery D2) with a module-owned form at `/dealer/apply` (keep the old URL redirecting to it). Fields as today, plus **Email** and **Password / Confirm password** (minimum 8 characters).
2. If the email already has a user: ask them to log in first, then prefill the form; the application links to the existing user.
3. On submit (in one transaction): create the company partner and contact, create the portal user via the standard signup method (verify; the user must be portal, not internal), create the application, attach files (category `application`), launch the activity plan, log the user in, and redirect to `/my/application`.
4. Auto-reply email (template `mail_application_received`): "Thanks — your application DA/00042 is in. Log in any time at <url> to see its status." This replaces the old auto-reply that pointed to a messaging portal without an account.

**Applicant view (`/my/application`)**
- Status pills: Received → Under review → Approved (Decision 1: simple status only; the internal checklist stays internal).
- Uploaded documents list.
- When `info_requested`: a message box showing staff's request and an upload form; submitting attaches files to the application, posts in chatter, moves the stage back to `under_review` and notifies the reviewer.
- A My Portal home tile "Dealer application" shows while the application is not approved.

**Staff flow (backend)**
- Menu: Sales → Dealers → Applications (list, kanban by stage, form). Default filter: open applications. Columns: name, company, contact, date, stage, open activities count, days waiting.
- On create: the plan creates four activities: **Verify address · Verify sales tax certificate · Verify business license · Signed dealer agreement**. Plan contents are configuration, so staff can add steps later without code.
- Button **Send dealer agreement**: creates a `sign.request` from the template with the contact as signer; on completion (hook on sign request state), mark the "Signed dealer agreement" activity done automatically and attach the signed PDF to the partner with category `application`.
- Button **Request more info**: wizard with a message (required) and a checklist of items; sets `info_requested`, emails the applicant (template `mail_application_info_requested`) with a link to `/my/application`.
- **Approve** button visible only when `checklist_done`. Wizard fields: price tier (pricelist, required, domain = dealer pricelists), credit limit, salesperson, payment terms (optional), "Enroll in dealer training" (checked). On confirm:
  1. Set the pricelist on the company partner (company-dependent property in the website's company), `credit_limit` + `use_partner_credit_limit`, `user_id`, payment terms.
  2. Add the Approved Dealer tag (base recomputes `rvsb_is_approved_dealer`).
  3. Set the applicant's `rvsb_portal_role = 'owner'`.
  4. Tag application attachments for the Documents tab; create `rvsb.dealer.certificate` records from the certificate details in the application (status `valid`, reviewed by the approver).
  5. Enroll in dealer training channels (documents module hook).
  6. Set stage `approved`, email `mail_application_approved` (welcome, sales rep contact, link to My Portal and Dealer Resources).
- **Reject**: wizard with a reason (internal) and an optional message to the applicant; email `mail_application_rejected`. The user remains a retail portal user.

**Migration of existing applications.** A server action or one-time script (documented in the README) that creates `rvsb.dealer.application` records for pending applicants from today's source (Discovery D2), creates their portal users without passwords (they receive a "set your password" invitation), and launches the plan.

**Interactions.** Approval flips Become a Dealer → Help & Feedback (base + fixes), populates Documents (documents), enrolls training (documents), sets credit and rep cards (account_info), sets the Owner role (roles).

**Edge cases.** Duplicate application from the same company (same EIN or email domain): warn staff on the form with a link to the earlier one. Sign request declined: activity stays open, reviewer notified. Approver forgets training enrollment: settings button to enroll all dealers.

**Tests.** Signup creates exactly one portal user and logs in; existing email path; plan activities created; info-request round trip; sign completion closes the activity; Approve hidden until checklist done; approval sets all six outcomes; reject path; access: one applicant cannot view another's application.

---

### 6.7 `rvsb_portal_roles` (Task 20)

**Purpose.** Let a dealer's Owner add their own staff and assign roles; enforce the role matrix on every page, route and record.

**Depends:** `rvsb_dealer_base`, `rvsb_portal_fixes`, `rvsb_portal_account_info`, `rvsb_portal_orders`, `rvsb_portal_addresses`, `rvsb_portal_documents`, `website_sale`, `account`. (The quotes and installer modules are built later and do their own `rvsb_can` checks, so roles does not depend on them.)

**Role matrix (source of truth is the table in base)**

| Role | Can do | Cannot do |
|---|---|---|
| Owner / Admin | Everything, including adding and removing users | — |
| Buyer | Place and view orders, cancel requests, pins, PO upload, export orders, manage ship-to addresses, quotes, tickets | Payments, credit, invoices, store credit, certificates, pricing export, user management |
| Accountant | Invoices, payments, statements, credit limit and usage, store credit, tax certificates, view and export orders, tickets | Place or cancel orders, PO upload, manage addresses, quotes, pricing export, user management |
| Viewer | Order status and tracking, Dealer Resources | Everything else |

**User management page (`/my/users`, permission `manage_users`)**
- List of the company's portal users: name, email, role, last login, status (active, invited, disabled).
- **Invite user**: name, email, role → create a child contact of the commercial partner, grant portal access (standard portal wizard method; verify), send the invitation email. If the email already belongs to a user of another company: refuse with "This email is linked to another account. Contact us."
- **Change role** (select), **Disable** (archive the portal user; keep the contact), **Re-send invite**.
- Guardrails: an Owner cannot demote or disable themselves if they are the last Owner; at least one Owner must exist.
- Every change posts to the company partner's chatter (who changed what) for audit.

**Enforcement, in three layers**
1. **UI:** home tiles, menus, buttons and columns are hidden with `rvsb_can` (each module already does this for its own features). This module adds the checks to standard Odoo portal pages: invoices (`view_invoices`), payment methods/pay buttons (`make_payments`), quotations/orders cart and "Accept & Pay" (`place_orders`/`make_payments`), and checkout.
2. **Routes:** override standard portal controllers for invoices (`/my/invoices*`), payment methods (`/my/payment_method`), and the website checkout and cart-add routes (verify Odoo 19 routes), calling `rvsb_require(...)` before `super()`. Users without `place_orders` see prices and products but the add-to-cart button is replaced with "Ask your account owner to order" and cart routes return 403.
3. **Record rules** (backstop, portal group only): `account.move` readable only when the user's role is owner/accountant; similar rule for `payment.token`. Write the rules with a Python-expression domain that tests `user.partner_id.rvsb_portal_role`. Verify that rule domains can reference user fields this way in Odoo 19.

**Existing users.** Post-install migration: every existing extra portal login under a dealer company keeps `owner` (Decision 5), so nobody loses access. Document how Casey's team can bulk-change roles in the backend (list view of contacts with the role column editable).

**Forced logout (Decision 5).** Every dealer portal user starts a fresh session under the role system.
- Add `rvsb_session_epoch` (Integer, default 0) to `res.users` and include it in the fields that make up the user's session token (override the method that lists session-token fields, `_get_session_token_fields` in recent versions — verify in Odoo 19). Incrementing the value invalidates every existing session for that user on their next request, without changing their password.
- **Go-live:** the post-install migration increments `rvsb_session_epoch` for all portal users linked to dealer companies (and only them, never internal users). Everyone is signed out and logs back in under their role.
- **Every role change or disable afterward** (from `/my/users` or the backend) increments the epoch for that user, so the new permissions apply from a clean login.
- Backend button for `group_rvsb_dealer_manager` on the company contact: **Sign out all users of this dealer**.
- Optional heads-up: a dismissible banner on My Portal for 7 days after go-live: "We've added team roles. Your account owner can manage users under My Portal → Users."
- Test: an HttpCase with an active portal session gets redirected to login after the migration or a role change; internal users' sessions are untouched.

**Backend.** Add `rvsb_portal_role` to the contact form (Sales/Contacts tab) and the portal-access wizard, visible to `group_rvsb_dealer_manager`.

**Pricing for sub-users.** Confirm that child contacts get the company's pricelist at checkout (commercial field behavior, Section 5). If not, add the pricelist to the commercial fields for portal pricing.

**Tests.** Full matrix test: for each role, request every portal route (HttpCase) and assert 200/403/redirect; record-rule tests reading invoices as each role; invite flow; last-Owner guard; cross-company isolation (a user of dealer A can never read dealer B's orders, invoices, addresses, documents, quotes, even by guessing IDs).

---

### 6.8 `rvsb_dealer_quotes` (Task 21)

**Purpose.** Dealers create branded quotes for their own customers at MAP, MSRP or a custom margin, and deliver them as PDF, print or email.

**Depends:** `rvsb_dealer_base`, `rvsb_portal_addresses`, `website_sale`, `mail`.

**Settings (per company)**

| Field | Type | Meaning |
|---|---|---|
| `rvsb_map_pricelist_id` | m2o `product.pricelist` | MAP prices (data supplied by Casey's team by Nov 23) |
| `rvsb_msrp_pricelist_id` | m2o `product.pricelist` | MSRP prices |
| `rvsb_quote_below_map` | Selection: `allow`, `warn` (default), `block` | Custom-margin quotes priced below MAP (Decision 6, confirmed: warn) |
| `rvsb_quote_validity_days` | Integer, default 30 | Default "valid until" |

**`res.partner` (commercial):** `rvsb_quote_logo` (Image, max 1024 px), `rvsb_quote_footer` (Text: dealer's terms, license number, contact line). Edited on `/my/quotes/branding`.

**New model `rvsb.dealer.quote`**

| Field | Type | Notes |
|---|---|---|
| `name` | Char, sequence per dealer `Q-<dealer short code>-0001` | |
| `partner_id` | m2o commercial partner (the dealer) | |
| `user_id` | m2o `res.users` | Creator |
| `company_id` | m2o `res.company` | |
| `customer_name`, `customer_email`, `customer_phone` | Char | The dealer's end customer |
| `customer_address_id` | m2o `res.partner` (domain: dealer's customer addresses) | Optional, from Phase 4 |
| `pricing_basis` | Selection: `map`, `msrp`, `margin` | |
| `margin_pct` | Float | Used when `margin`: price = dealer cost × (1 + margin%) (markup on cost). Show the resulting gross margin % on screen to avoid confusion. Confirmed: markup on cost (Section 10, decision 15) |
| `line_ids` | o2m `rvsb.dealer.quote.line` | |
| `labor_lines` | o2m (description, amount) | Optional install labor / misc lines added by the dealer |
| `notes` | Html | |
| `valid_until` | Date | |
| `state` | Selection: `draft`, `sent`, `accepted`, `converted` | Accepted is set manually by the dealer |
| Totals | Monetary computed | Subtotal, labor, total; tax line optional (dealer enters a tax %; we don't calculate their local tax) |

`rvsb.dealer.quote.line`: `product_id`, `quantity`, `unit_price` (computed from basis, editable per line when basis = margin), `dealer_cost` (from the dealer's pricelist; **never printed**), `below_map` flag.

**Portal**
- `/my/quotes`: list (search, state filter), New quote.
- Editor `/my/quotes/<id>`: product search (published, sale_ok products; JSON autocomplete by SKU/name), quantity, pricing basis selector, margin input, per-line price override (margin mode), labor lines, customer details, notes, valid-until. Live totals. Dealer-only columns (cost, profit) visible on screen only.
- Below-MAP: per `rvsb_quote_below_map`: `warn` shows a yellow warning on the line and a confirmation before sending; `block` prevents saving a price below MAP.
- Actions: **Download PDF**, **Print** (opens PDF in a new tab), **Email to customer** (send to `customer_email` through `mail.mail` with the PDF attached, reply-to the dealer user's email, from the company's outgoing alias, subject "Quote <name> from <Dealer>"), **Duplicate**, **Mark accepted**, **Order these items** (adds the quote's product lines to the dealer's cart at the dealer's own price via the current cart API; sets state `converted`; stores the resulting order on the quote).

**PDF report (QWeb, `report_rvsb_dealer_quote`)**
- Header: dealer logo and dealer company name/address/phone/email. **No RV Solar branding, logo or pricing anywhere.** Use a custom paper layout, not the company's external layout (which would print RV Solar's header).
- Body: quote number, date, valid until, customer block, lines (SKU, description, qty, unit price, line total), labor lines, subtotal, tax (if entered), total, notes, dealer footer.
- Product descriptions: the website description (short) without internal notes.

**Security.** Quotes are visible only to users of the owning commercial partner. `create_quotes` permission. Dealer cost is never rendered in the PDF or email.

**Interactions.** Uses Phase 4 customer addresses; the MSRP pricelist setting is reused by the Documents pricing export; roles hide quotes for Accountant/Viewer.

**Tests.** Price computation for each basis; below-MAP warn/block; PDF contains no RV Solar strings or dealer cost (assert on rendered HTML); email attachment; order conversion uses the dealer's price; isolation between dealers.

---

### 6.9 `rvsb_installer_locator` (Task 22)

**Purpose.** Public "Find a local installer" page listing dealers who opt in and are approved by staff.

**Depends:** `rvsb_dealer_base`, `website_crm_partner_assign` (Resellers; verify name in Odoo 19), `website`.

**Settings:** `rvsb_installer_grade_id` (m2o partner grade "Installer", created by data file if missing).

**`res.partner` (commercial) fields:** `rvsb_installer_optin` (Boolean), `rvsb_installer_state` (`none`, `requested`, `listed`, `declined`), `rvsb_installer_services` (m2m tags: RV, Marine, Off-grid, Residential solar), `rvsb_installer_radius` (Integer miles), `rvsb_installer_blurb` (Text, 300 chars).

**Dealer side.** On My Portal (Owner only), a card "Get listed as a local installer": checkbox, services, service radius, short description, preview of the listing. Saving with opt-in sets `requested` and notifies the `installer_listing` alert list. Opting out unpublishes immediately.

**Staff side.** On the contact form, **List installer** / **Decline** buttons. Listing sets the grade, publishes the partner on the partner directory (verify publication field) and sets `listed`. The listing shows only the business name, city/state, phone, website, services and blurb — never the street address unless the dealer ticks "Show my street address".

**Public page.** Use the partner directory's page and map (configured for the RV Solar website), filtered to the Installer grade, with search by ZIP/city and a services filter. Retitle the page "Find a local installer". Add a "Find a local installer" button to the website header or footer (Casey picks the spot) linking to it. Approved dealers who never opt in never appear.

**Tests.** Opt-in → requested → listed → visible; opt-out removes from the page immediately; declined never visible; street address hidden by default.

---

## 7. Stripe Link on My Payments

Opening My Payments builds Stripe's card form with the customer's saved email. Link then texts a verification code before the customer asks to pay. `int_website_customizations` turns that prompt off (`wallets.link` = `never`) when the card form is created. Card payments and saved cards stay. Link is not a separate payment method on the Stripe provider.

---

## 8. Cross-module interaction map

| Event | Triggered in | Effects in other modules |
|---|---|---|
| Dealer approved | onboarding | base: dealer flag true → fixes: Become a Dealer hidden, Help & Feedback shown → account_info: rep and credit cards appear → documents: application files visible, certificates created, training enrolled → roles: applicant is Owner → installer_locator: opt-in card available |
| Approved Dealer tag removed or pricelist changed to retail | backend | base: dealer flag false → reverse of the above for UI (data is kept) |
| Cancel request submitted | orders | activity + email to staff; picking shows warning banner |
| Cancel approved with store credit | orders | credit note + top-up invoice reconciled; eWallet balance up → store credit card on My Portal; usable at checkout |
| Certificate nearing expiry | documents (cron) | emails to Owner/Accountant users; staff activity |
| Address set residential | addresses | order and picking show liftgate flag; Shippo bridge sends residential flag |
| User role changed | roles | every module's `rvsb_can` checks change immediately (no cache, or clear cache on write) |
| Quote converted | quotes | lines added to cart at dealer price → normal checkout → normal order flow |

Shared settings page: every module adds its fields to one "Dealer Portal" block in Website settings, grouped by module heading.

---

## 9. Testing strategy and full regression checklist

**Automated tests (every module):**
- `TransactionCase` for model logic (computes, state transitions, accounting entries, cron).
- `HttpCase` for routes (status codes per role, ownership checks) and at least one JS tour per page with interactive behavior (forms, pins, quote editor).
- Tag tests `post_install`, `-at_install`. Run locally with `--test-tags /rvsb_<module>`; Odoo.sh runs them on each development-branch build.
- Test data: create partners, products and pricelists in `setUpClass`; never depend on production data.

**Staging data (from the Kickoff Guide):** retail customer; approved dealer with credit limit, rep and 300+ orders (shipped with tracking, backordered, unshipped); pending applicant; dealer with three extra logins.

**Full regression before each production deploy (manual, about 20 minutes):**
1. Log in as retail: My Portal home, orders, addresses, payments; Become a Dealer visible; Dealer Resources not reachable by URL.
2. Log in as dealer Owner: all tiles; search orders by each field; backorders; pin and reorder; export both files; PO upload (XLSX + PDF); request cancellation; addresses split and checkout with a residential address; documents and pricing download; resources; Help & Feedback each form; quote create → PDF → email → convert; installer opt-in.
3. Staff: approve a cancel request with store credit; review a certificate; run a full application from signup to approval.
4. Log in as Buyer, Accountant and Viewer: check the matrix.
5. Place one real-card checkout on production after deploy (refund it afterward).

---

## 10. Decisions log (defaults in effect; confirm with Casey)

These defaults were recommended before kickoff. The build uses them unless Casey says otherwise. When confirmed or changed, update this table and the relevant module spec.

| # | Decision | Default in this spec | Confirmed? |
|---|---|---|---|
| 1 | Applicant sees simple status or full checklist | Simple status (Received → Under review → Approved) | ☐ |
| 2 | Refund options on approved cancellations | Both; store credit listed first; staff can override | ☐ |
| 3 | Accountant role permissions | As in Section 6.7 | ☐ |
| 4 | Default category for existing addresses | Business; dealers recategorize | ☐ |
| 5 | Default role for existing extra logins | Owner, and every dealer portal user is logged out when roles go live (confirmed by Casey) | ☑ |
| 6 | Quotes priced below MAP | Warn but allow (confirmed by Casey) | ☑ |
| 7 | Who gets cancel alerts, Help & Feedback tickets and other staff alerts | Per-alert lists with tick boxes for every internal user, optional whole groups and extra inboxes, editable any time (base, Alert lists) (confirmed by Casey) | ☑ |
| 8 | Dealer pricelist list | From Discovery D1 | ☐ |
| 9 | Pin limit | 5 (confirmed by Casey) | ☑ |
| 10 | Cancel flow | Request → staff decide → no refund until confirmed (confirmed by Casey) | ☑ |
| 11 | Credit display | Dollar amounts plus usage bar (confirmed by Casey) | ☑ |
| 12 | Roles | Owner, Buyer, Viewer plus Accountant (confirmed by Casey) | ☑ |
| 13 | Application documents | Arrive with the application; reps may request more (confirmed by Casey) | ☑ |
| 14 | Store-credit accounting (credit note + top-up invoice reconciled) | Needs accountant sign-off before production | ☐ |
| 15 | Quote "custom margin" meaning | Markup on dealer cost; show resulting margin % (confirmed by Casey) | ☑ |
| 16 | Expired tax certificate | Notify only; do not block orders (confirmed by Casey) | ☑ |
| 17 | Installer listing shows street address | Hidden unless the dealer opts in | ☐ |
| 18 | Where the current phase is built | Grant, 2026-11-08: no new module. Tasks 2–5 go in `int_website_customizations` (password fields, Password & Security, Become a Dealer) and `int_helpdesk_customizations` (Help & Feedback). Follow the repo `int_*` module rule. Section 3's `rvsb_*` modules stay the behavior spec for later phases until Grant says to create them. All of this work stays on `staging1`. | ☑ Grant |
| 19 | Ticket types on Odoo 19 | This database has no `helpdesk.ticket.type` and no `ticket_type_id`. The four Help & Feedback kinds are `helpdesk.tag` records. Company settings that Section 6.1 calls ticket-type fields point at `helpdesk.tag`. | ☑ verified live 2026-11-08 |
| 20 | Which team, and dealer vs retail | Grant, 2026-11-08: do not create a helpdesk team. Returns and warranty claims use the existing returns team (RVSB Returns). Feedback and part requests use the existing general inquiries team. Keep the four kind tags. The ticket copies the contact's Tags field and uses the same names. It does not invent a Customer type from the pricelist. | ☑ Grant |
| 21 | Dealer account email | Grant, 2026-11-08: retail guests can still create an account after checkout. When staff approve a dealer, the account email sends a create-password link if they have no login. If they already created an account at checkout, keep that login and email them to sign in. Do not create a second user. | ☑ Grant |
| 22 | Dealer invite on the opportunity | Grant, 2026-11-08: **Create Dealer Account** on the CRM opportunity opens a wizard. Staff pick the pricelist. Confirm sets that pricelist on the commercial partner, adds the contact tag **RVSB Dealer** (create the tag by that name if it is missing; do not hardcode an id), then sends the account email from decision 21. A later helpdesk ticket copies that contact tag onto the ticket. | ☑ Grant |

---

## 11. Parked work

**Blind shipping.** A checkout checkbox so the label ships from the dealer's name and the packing slip carries no RV Solar branding or pricing. Depends on whether the Shippo add-on supports a per-order ship-from override. **Do not build.** When un-parked, it hangs off Phase 4 customer addresses and the Shippo bridge module.

**Dealer agreement with MAP policy.** Legal document drafted separately and reviewed by an attorney. The final PDF becomes the Sign template in Phase 6 by Nov 30.

---

## 12. Claude Code prompt library

Use one prompt per session. Replace nothing; the prompts reference this file. Each prompt assumes `CLAUDE.md` is at the repository root.

### 12.0 Discovery (run once, before any module)

```
Read CLAUDE.md and docs/dealer-portal/SPEC.md sections 2, 3 and 5.
Do not write module code yet.
1. Inspect this repository: list every custom module, its dependencies, and every
   portal/website_sale template or controller it inherits.
2. Using the Odoo 19 source available in this environment, complete the Section 5
   verification checklist: for each item give the real template ID, method name,
   field name or route, with file path and line number.
3. Write the results to docs/dealer-portal/DISCOVERY.md, plus a list of the
   Section 2 questions you could not answer from code (I will answer those).
```

### 12.1 `rvsb_dealer_base`

```
Read CLAUDE.md, docs/dealer-portal/SPEC.md (sections 3, 4, 6.0) and
docs/dealer-portal/DISCOVERY.md.
Plan first: list every file you will create, every model/field, every inherited
template with its exact xpath anchor from the Odoo 19 source. Wait for my OK.
Then build addons/rvsb/rvsb_dealer_base exactly per section 6.0, including the
RVSB_PERMISSIONS table, rvsb_can(), the controller helper, the portal_tile
template, the website.menu visibility field, the rvsb.alert.list model with its
tick-box form, _rvsb_notify helper and settings block, and settings.
Write the tests listed in 6.0 and run them with --test-tags /rvsb_dealer_base.
Finish by checking each convention in section 4 and reporting pass/fail.
```

### 12.2 `rvsb_portal_fixes`

```
Read CLAUDE.md, SPEC.md sections 4, 5 and 6.1, and DISCOVERY.md (D2, D3, D7).
rvsb_dealer_base is installed. Plan first and wait for my OK.
Build addons/rvsb/rvsb_portal_fixes per section 6.1: Task 2 password fields,
Task 3 rename, Task 4 Become a Dealer visibility (use the D3 finding),
Task 5 Help & Feedback hub, four forms, own controller, helpdesk tickets,
rate limit, validation. Use rvsb_dealer_base.portal_tile for tiles.
Write and run the 6.1 tests. Then list the manual configuration steps
(helpdesk team, ticket types, stage email) for the README.
```

### 12.3 `rvsb_portal_account_info`

```
Read CLAUDE.md, SPEC.md sections 4, 5 and 6.2, and DISCOVERY.md.
Plan first (include the exact My Orders template and controller you will extend,
and how you avoid per-row queries). Wait for my OK.
Build per section 6.2: tracking column, sales rep card, credit card with bar and
color thresholds, and the rvsb_account_cards slot for later modules.
Write and run the 6.2 tests, including a check that portal credit figures equal
the backend partner figures.
```

### 12.4 `rvsb_portal_orders`

```
Read CLAUDE.md, SPEC.md sections 4, 5, 6.3 and 10 (decisions 2, 9, 10, 14),
and DISCOVERY.md (cart API, reorder, loyalty, payment refund findings).
This is the largest module. Plan first, task by task (9 to 14), and wait for my OK.
Then implement ONE task at a time in this order: 9, 10, 12, 13, 14, 11.
After each task, run its tests and stop for my review before the next.
For Task 11, show me the exact journal entries created in each refund path
before writing the code that creates them.
```

### 12.5 `rvsb_portal_addresses` and the Shippo bridge

```
Read CLAUDE.md, SPEC.md sections 4, 5, 6.4 and decision 4, and DISCOVERY.md
(address routes, D5 Shippo add-on).
Plan first, including the migration script and the exact Shippo add-on method you
will override. Wait for my OK.
Build rvsb_portal_addresses and the auto-install bridge rvsb_portal_addresses_shippo
per section 6.4. Write and run the tests, including a mocked Shippo payload test.
```

### 12.6 `rvsb_portal_documents`

```
Read CLAUDE.md, SPEC.md sections 4, 5, 6.5 and decision 16, and DISCOVERY.md (D2, D6).
Plan first (model, cron, controllers, blog/eLearning restriction approach).
Wait for my OK.
Build per section 6.5: certificate model and lifecycle, review activities, reminder
cron with de-duplication, Documents page, pricing XLSX, Dealer Resources page with
dealer-only blog enforcement and the training enrollment hook used by onboarding.
Write and run the 6.5 tests (back-date expirations to test each reminder).
```

### 12.7 `rvsb_dealer_onboarding`

```
Read CLAUDE.md, SPEC.md sections 4, 5, 6.6, 8 and decision 1, and DISCOVERY.md (D2).
Plan first: the application model, the signup transaction, the activity plan launch,
the sign-request completion hook, the approve wizard's six outcomes, and the
migration of existing applications. Wait for my OK.
Build per section 6.6. Write and run the 6.6 tests, including a full
signup-to-approval HttpCase.
```

### 12.8 `rvsb_portal_roles`

```
Read CLAUDE.md, SPEC.md sections 4, 5, 6.0 (permission table), 6.7 and decisions 3 and 5.
Plan first: list every standard Odoo portal/website route you will guard, with file
path from the Odoo 19 source, and every record rule. Wait for my OK.
Build per section 6.7: user management page, invite/role/disable, last-Owner guard,
three enforcement layers, migration for existing users, and the forced-logout
session epoch (go-live migration, per-user on role change, dealer-wide button).
Write the full matrix HttpCase test (every role x every route) and the
cross-company isolation tests. Run them all.
```

### 12.9 `rvsb_dealer_quotes`

```
Read CLAUDE.md, SPEC.md sections 4, 5, 6.8 and decisions 6 and 15.
Plan first: models, editor page (JS approach), price computation, PDF layout that
avoids the company external layout, email sending, cart conversion. Wait for my OK.
Build per section 6.8. Tests must assert the rendered PDF HTML contains no
"RV Solar" string and no dealer cost.
```

### 12.10 `rvsb_installer_locator`

```
Read CLAUDE.md, SPEC.md sections 4, 5, 6.9 and decision 17, and DISCOVERY.md
(Resellers module findings).
Plan first and wait for my OK. Build per section 6.9 and run its tests.
```

### Prompts for common situations

- **Build failed on Odoo.sh:** "Here is the full build log from Odoo.sh: <paste>. Find the root cause, explain it, and fix it. Do not change unrelated files."
- **Template inheritance broke after an update:** "This xpath no longer matches: <paste error>. Open the current Odoo 19 template, find a stable anchor and update the inheritance. Explain why the new anchor is stable."
- **Behavior doesn't match spec:** "Section 6.X says <quote>. Current behavior: <describe>. Steps: <list>. Fix it and add a regression test."
- **Spec change from Casey:** "Casey changed decision N to <new value>. Update SPEC.md section 10 and the affected module spec first, show me the diff, then update code and tests."
- **Before every deploy:** "Re-read SPEC.md section 4 and the module's spec. Review the module against both and list any gaps. Then run all rvsb tests."

---

## 13. Schedule reference

| Week | Dates | Goes live | On staging for Friday review |
|---|---|---|---|
| 0 | Nov 5–6 | — | Staging branch, test data, discovery |
| 1 | Nov 9–13 | base, fixes (Phase 1), account_info (Phase 2) | orders (Phase 3) |
| 2 | Nov 16–20 | orders, addresses (Phases 3–4) | documents (Phase 5) |
| 3 | Nov 23–25 | documents | onboarding (Phase 6) |
| 4 | Nov 30–Dec 4 | onboarding, roles, quotes, installer locator (Phases 6–8) | Full regression |

If behind at the end of week 3, Phase 8 (quotes, installer locator) moves one week. Nothing else slips.
