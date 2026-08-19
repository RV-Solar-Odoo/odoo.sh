#!/usr/bin/env python3
"""
RVSB — pull Studio customizations and configuration out of the Odoo Online
(SaaS 19.2) database via XML-RPC, ahead of the 19.0 rebuild on Odoo.sh.

Read-only. Nothing here writes to the source database.
"""

import json
import os
import sys
import xmlrpc.client
from collections import defaultdict

URL = os.environ.get("ODOO_URL", "").rstrip("/")
DB = os.environ.get("ODOO_DB", "")
USER = os.environ.get("ODOO_USER", "")
KEY = os.environ.get("ODOO_KEY", "")
OUTDIR = os.environ.get("ODOO_AUDIT_DIR", "studio_audit")

if not all([URL, DB, USER, KEY]):
    sys.exit("Set ODOO_URL, ODOO_DB, ODOO_USER and ODOO_KEY first.")

os.makedirs(OUTDIR, exist_ok=True)

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, USER, KEY, {})
if not uid:
    sys.exit("Authentication failed — check DB name, login and API key.")

models = xmlrpc.client.ServerProxy(
    f"{URL}/xmlrpc/2/object", allow_none=True, use_datetime=False
)


def call(model, method, *args, **kw):
    return models.execute_kw(DB, uid, KEY, model, method, list(args), kw)


def search_read(model, domain=None, fields=None):
    """search_read with a high limit. limit=0 returns nothing on 19.2."""
    kw = {"limit": 10000}
    if fields:
        kw["fields"] = fields
    return call(model, "search_read", domain or [], **kw)


def dump(name, payload):
    path = os.path.join(OUTDIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
    count = len(payload) if hasattr(payload, "__len__") else "?"
    print(f"  {name:24s} {count:>6} -> {path}")


def safe(label, fn, default=None):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - audit script, keep going
        print(f"  !! {label} failed: {exc}")
        return default if default is not None else []


print(f"\nConnected to {DB} as uid {uid}\n")

# ---------------------------------------------------------------------------
# 1. Ground truth: every record Studio ever created.
# ---------------------------------------------------------------------------
print("Studio records")

studio_xmlids = safe(
    "studio xmlids",
    lambda: search_read(
        "ir.model.data",
        [("module", "=", "studio_customization")],
        ["model", "res_id", "name", "create_date", "write_date"],
    ),
)
dump("studio_xmlids", studio_xmlids)

by_model = defaultdict(list)
for row in studio_xmlids:
    by_model[row["model"]].append(row["res_id"])

dump("studio_summary", {model: len(ids) for model, ids in sorted(by_model.items())})

# ---------------------------------------------------------------------------
# 2. Resolve those IDs into the actual record contents.
# ---------------------------------------------------------------------------
print("\nStudio record contents")

studio_contents = {}
for model, ids in sorted(by_model.items()):
    rows = safe(
        model,
        lambda m=model, i=ids: search_read(m, [("id", "in", i)]),
    )
    if rows:
        studio_contents[model] = rows
        print(f"  {model:36s} {len(rows):>5}")
dump("studio_contents", studio_contents)

# ---------------------------------------------------------------------------
# 3. Custom models and fields (catches manual work done outside Studio too).
# ---------------------------------------------------------------------------
print("\nCustom schema")

dump(
    "custom_models",
    safe("custom models", lambda: search_read(
        "ir.model", [("state", "=", "manual")],
        ["model", "name", "info", "transient"],
    )),
)

dump(
    "custom_fields",
    safe("custom fields", lambda: search_read(
        "ir.model.fields", [("state", "=", "manual")],
        ["model", "name", "field_description", "ttype", "relation",
         "relation_field", "required", "readonly", "store", "index",
         "copied", "compute", "related", "depends", "on_delete",
         "domain", "help", "tracking", "selection_ids", "group_expand"],
    )),
)

dump(
    "x_fields",
    safe("x_ fields", lambda: search_read(
        "ir.model.fields", [("name", "=like", "x_%")],
        ["model", "name", "field_description", "ttype", "relation",
         "state", "required", "readonly", "store", "compute", "related",
         "help", "selection_ids"],
    )),
)

dump(
    "selection_values",
    safe("selection values", lambda: search_read(
        "ir.model.fields.selection", [],
        ["field_id", "value", "name", "sequence"],
    )),
)

# ---------------------------------------------------------------------------
# 4. Settings
# ---------------------------------------------------------------------------
print("\nSettings")

setting_fields = safe(
    "settings schema",
    lambda: call("res.config.settings", "fields_get", [],
                 attributes=["string", "type", "help"]),
    default={},
)

if setting_fields:
    values = safe(
        "settings values",
        lambda: call("res.config.settings", "default_get",
                     sorted(setting_fields.keys())),
        default={},
    )
    dump("settings", {
        key: {
            "value": values.get(key),
            "label": setting_fields.get(key, {}).get("string"),
            "type": setting_fields.get(key, {}).get("type"),
        }
        for key in sorted(values)
    })

dump(
    "config_params",
    safe("config params", lambda: search_read(
        "ir.config_parameter", [], ["key", "value"],
    )),
)

# ---------------------------------------------------------------------------
# 5. Everything else the rebuild has to reproduce by hand.
# ---------------------------------------------------------------------------
print("\nConfiguration inventory")

INVENTORY = [
    ("modules", "ir.module.module", [("state", "=", "installed")],
     ["name", "shortdesc", "latest_version", "author"]),
    ("automations", "base.automation", [],
     ["name", "model_id", "trigger", "filter_domain", "active",
      "trigger_field_ids", "action_server_ids"]),
    ("server_actions", "ir.actions.server", [],
     ["name", "model_id", "state", "code", "usage", "sequence",
      "update_path", "value", "child_ids"]),
    ("window_actions", "ir.actions.act_window", [],
     ["name", "res_model", "view_mode", "domain", "context", "target"]),
    ("reports", "ir.actions.report", [],
     ["name", "model", "report_name", "report_type", "print_report_name"]),
    ("access_rights", "ir.model.access", [],
     ["name", "model_id", "group_id", "perm_read", "perm_write",
      "perm_create", "perm_unlink", "active"]),
    ("record_rules", "ir.rule", [],
     ["name", "model_id", "domain_force", "groups", "global",
      "perm_read", "perm_write", "perm_create", "perm_unlink"]),
    ("groups", "res.groups", [], ["name", "implied_ids"]),
    ("users", "res.users", [("active", "in", [True, False])],
     ["login", "name", "active", "share"]),
    ("mail_templates", "mail.template", [],
     ["name", "model_id", "subject", "email_from", "email_to",
      "partner_to", "body_html", "report_template_ids"]),
    ("sequences", "ir.sequence", [],
     ["name", "code", "prefix", "suffix", "padding", "number_next_actual",
      "number_increment", "implementation", "company_id"]),
    ("filters", "ir.filters", [],
     ["name", "model_id", "domain", "context", "sort", "is_default"]),
    ("cron_jobs", "ir.cron", [],
     ["name", "model_id", "state", "active", "interval_number",
      "interval_type", "nextcall"]),
    ("currencies", "res.currency", [("active", "=", True)],
     ["name", "symbol", "rounding"]),
    ("companies", "res.company", [],
     ["name", "currency_id", "country_id", "vat", "email", "phone",
      "website", "street", "street2", "city", "zip", "state_id"]),
]

for name, model, domain, fields in INVENTORY:
    dump(name, safe(name, lambda m=model, d=domain, f=fields:
                    search_read(m, d, f)))

# ---------------------------------------------------------------------------
# 6. Modified standard views — things changed outside Studio.
# ---------------------------------------------------------------------------
print("\nView customizations")

dump(
    "noupdate_views",
    safe("modified views", lambda: search_read(
        "ir.ui.view", [("arch_updated", "=", True)],
        ["name", "model", "type", "inherit_id", "arch_db", "active", "key"],
    )),
)

print(f"\nDone. {len(os.listdir(OUTDIR))} files in ./{OUTDIR}/\n")
print("Next: diff studio_summary.json against the contents of")
print("studio_customization.zip. Anything present here and absent there")
print("is a gap the export missed.\n")
