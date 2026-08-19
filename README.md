# Odoo.sh custom modules

Every custom module is prefixed with `int_` and authored `Internal`.
Search Apps for `int_` to see only ours.

| Module | Role |
| --- | --- |
| `int_base` | Umbrella app — install this |
| `int_inventory_customizations` | Product fields, form, and categories from the 19.2 Studio export |

`int_inventory_customizations` auto-installs with `int_base` when Inventory / Purchase are already present.
New app customizations go in `int_<app>_customizations` (for example `int_helpdesk_customizations`) and depend on `int_base`.
