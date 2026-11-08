# CLAUDE.md — RV Solar & Battery Odoo repository

## This checkout

Grant placed the dealer-portal spec here on 2026-11-08 so later sessions can find it.

- Read `docs/dealer-portal/SPEC.md` (v1.1, November 6, 2026) and `docs/dealer-portal/DISCOVERY.md` before dealer-portal work. The Word original is `docs/dealer-portal/Dealer_Portal_Module_Build_Spec.docx`.
- The site is not live. Through 2026-12-09, dealer-portal commits go straight to `main`. Grant said so on 2026-11-09. After that date, ask before pushing `main`.
- Do not add a module for the current phase. Implement Tasks 2–5 in the existing related modules: portal password, the Password & Security rename, and Become a Dealer in `int_website_customizations`; Help & Feedback in `int_helpdesk_customizations`. Module names, manifests, and versions still follow `.cursor/rules/int-modules.mdc` (`int_<app>_customizations`, author Internal, license LGPL-3). The `rvsb_*` map below is the behavior spec for later phases until Grant says to create those modules.
- Behavior, fields, copy, upload limits, and the 10-tickets-per-hour limit still come from SPEC.md Section 6.1. Task 1 (Stripe Link) is configuration only.

## Project
- Odoo 19 **Enterprise**, hosted on **Odoo.sh**, connected to this GitHub repository.
- Multi-company is enabled (RV Solar & Battery and Nomadiq share one database). Everything must be company-aware.
- Current project: the dealer portal. The full spec is `docs/dealer-portal/SPEC.md`; discovery findings are in `docs/dealer-portal/DISCOVERY.md`. Read both before working on any `rvsb_*` module.
- Custom dealer-portal modules live in `addons/rvsb/`. Other custom modules already in the repo (for example `website_sale_tag_groups`, the Victron E-Order stock module) must not be broken. Check for template and controller overlap before inheriting the same views.

## How to work
- One module per session, in the order given in SPEC.md Section 3.
- **Plan before code.** Read the spec section, open the real Odoo 19 source files you will inherit, and present a file-by-file plan with exact template IDs, xpath anchors, methods and fields. Wait for approval.
- **Verify, don't assume.** Odoo APIs changed between 16 and 19. Anything marked *(verify)* in the spec, and anything in SPEC.md Section 5, must be checked against the Odoo 19 source and recorded in DISCOVERY.md before it is used.
- Implement large modules one task at a time, running tests after each.
- If the spec does not cover something, ask. If you must decide, record it in the module README under "Decisions made during build" and in SPEC.md Section 10.
- If a spec change is requested, update SPEC.md first, show the diff, then change code and tests.

## Hard rules
- Never modify Odoo core or Enterprise source. Inherit or configure only. No monkey-patching.
- Never hardcode database IDs (companies, websites, pricelists, users, teams). Use settings on `res.company` exposed in Settings → Website → Dealer Portal, or XML IDs created by the module.
- Portal code returns only the logged-in user's commercial partner data. Build the ownership-constrained domain **before** any `sudo()`. Validate all user input.
- Every portal route checks a permission with `rvsb_require('<permission>')` from `rvsb_dealer_base`; templates hide UI with `request.env.user.rvsb_can('<permission>')`. The permission table lives only in `rvsb_dealer_base`.
- Uploaded files become private `ir.attachment` records on the owning record; validate type and size.
- No changes to production without a staging test and Casey's sign-off.

## Conventions
- Module names `rvsb_<area>`; new models `rvsb.<thing>`; new fields on existing models prefixed `rvsb_`.
- Manifest version `19.0.x.y.z`; bump on data or view changes; add migrations for existing data.
- Views: `<list>` not `<tree>`; `invisible=`/`readonly=` expressions, no `attrs`.
- `@api.model_create_multi` on create overrides; avoid N+1 queries on portal list pages.
- Front-end assets in `web.assets_frontend`; reuse portal card markup via `rvsb_dealer_base.portal_tile` so new tiles match existing ones; test at 375 px wide.
- User-facing name for the account area is **My Portal**.
- Each module has `README.md` (purpose, settings, manual configuration steps, dependencies, decisions) and `tests/`.

## Testing
- `TransactionCase` for logic; `HttpCase` for routes and per-role access; JS tours for interactive pages.
- Tag tests `post_install`, `-at_install`; run with `--test-tags /<module_name>`.
- Create all test data in the test; never rely on database content.
- Before finishing a module: run all `rvsb_*` tests, re-read SPEC.md Section 4, and report each convention as pass/fail.

## Deploy flow (Odoo.sh)
feature/dev branch → staging branch (fresh copy of production data) → Casey signs off on Friday → manual production backup → merge to production → smoke test (SPEC.md Section 9).
