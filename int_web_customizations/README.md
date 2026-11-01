# Nomadiq Backend Theme (Odoo 19 Enterprise)

Black / gray back office with Nomadiq blue (`#3a4efd`, the website's `--brand-blue`) as the single accent, and the Nomadiq wordmark in the top bar. Assets only: no Python, no data, no core edits. Uninstalling restores the stock look.

## What changes

| Area | Result |
|---|---|
| Top bar | `#141414`, Nomadiq wordmark at far left, light-gray menu text, white current app, blue notification badges |
| Primary buttons (New, Confirm, Send…) | Nomadiq blue, darker on hover |
| Links, checkboxes, focused inputs, active filters / view switcher, selected rows | Blue / blue tint |
| Current pipeline step (Quotation → Sent → Order) | Charcoal with white text |
| Active tab in forms | Blue top edge |
| Chatter "Send message" | Charcoal |
| Apps home (Enterprise) | Black (a company background image set in Settings still wins) |
| Everything else | Light gray background, white sheets — reads like stock Odoo |

Per-user **dark mode** still works; in dark mode only the top bar and logo are themed, the rest stays Odoo's dark palette.

## Install on Odoo.sh

1. The module is `int_web_customizations`, next to the other custom modules.
2. Commit and push to a **development or staging branch** first. Odoo.sh builds it automatically.
3. In that build: **Apps → clear the "Apps" filter → search "Web Customizations" → Install.**
   If it does not show up, turn on developer mode → Apps → **Update Apps List**, then search again.
4. Hard-refresh the browser (Ctrl/Cmd + Shift + R). Check a list view, a form with a pipeline, and the apps home.
5. Merge to production and install there the same way.

## Two settings to do once in the UI (no code)

* **Settings → Companies → Nomadiq**: upload the **Logo** (used on login page, PDF reports, emails) and the **Favicon** (browser tab).
* **Settings → General Settings → Companies → Document Layout**: pick layout, set primary/secondary colors so PDF quotes and invoices match.

## Tuning

All colors are in two places and nowhere else:

* `static/src/scss/primary_variables.scss` — the palette block at the top. This file is prepended before every Odoo variable, so it may contain **literal values only** (no `$o-…` from Odoo).
* `static/src/scss/theme.scss` — same palette repeated, plus the logo and a few explicit overrides via the CSS custom properties Odoo reads (`--NavBar-*`, `--btn-*`, `--table-active-*`, `--o-statusbar-*`).

Top-bar logo: replace `static/src/img/nomadiq_logo_nav.png` (transparent PNG, ~290×60, light color — it sits on black). Size on screen is set in `theme.scss` (`width: 92px; height: 19px`).

After editing SCSS on Odoo.sh, push; the build recompiles assets. On a local instance: upgrade the module or clear assets (developer mode → bug icon → Regenerate Assets Bundles).

## Why it is built this way

* `web._assets_primary_variables` (prepend) is Odoo's documented hook for backend themes: everything Odoo and Bootstrap derive from `$o-brand-primary`, `$o-navbar-*`, `$o-component-active-*` follows automatically.
* `web.assets_backend` adds the logo with a `::before` on `.o_main_navbar` instead of overriding the navbar template, so Odoo upgrades cannot break an XPath.
* The explicit overrides in `theme.scss` only use custom properties Odoo already exposes, so there is no `!important` fight with core styles.
