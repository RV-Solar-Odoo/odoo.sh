# Odoo.sh custom modules

Every custom module is prefixed with `int_` and authored `Internal`.
Search Apps for `int_` to see only ours.

| Module | Role |
| --- | --- |
| `int_base` | Umbrella app — install this |
| `int_inventory` | Product fields, form, and categories from the 19.2 Studio export |

`int_inventory` auto-installs with `int_base` when Inventory / Purchase are already present.
New app customizations go in `int_<app>` (for example `int_helpdesk`) and depend on `int_base`.
