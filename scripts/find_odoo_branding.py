#!/usr/bin/env python3
"""
List every database record that still says "Powered by" Odoo.

Read-only. Nothing here writes to the database. Pages and emails that come from
JavaScript (Point of Sale, Attendance kiosk) aren't stored records, so they won't show.
"""

import os
import sys
import xmlrpc.client

URL = os.environ.get("ODOO_URL", "").rstrip("/")
DB = os.environ.get("ODOO_DB", "")
USER = os.environ.get("ODOO_USER", "")
KEY = os.environ.get("ODOO_KEY", "")

if not all([URL, DB, USER, KEY]):
    sys.exit("Set ODOO_URL, ODOO_DB, ODOO_USER and ODOO_KEY first.")

TARGETS = [
    ("ir.ui.view", "arch_db", ["name", "key"]),
    ("mail.template", "body_html", ["name"]),
    ("mailing.mailing", "body_arch", ["subject"]),
    ("res.company", "report_footer", ["name"]),
]

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, USER, KEY, {})
if not uid:
    sys.exit("Authentication failed — check DB name, login and API key.")
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

total = 0
for model, field, labels in TARGETS:
    try:
        rows = models.execute_kw(
            DB, uid, KEY, model, "search_read",
            [[(field, "ilike", "powered by")]],
            {"fields": labels, "context": {"active_test": False}},
        )
    except xmlrpc.client.Fault as exc:
        print(f"{model}: skipped ({exc.faultString.strip().splitlines()[-1]})")
        continue
    print(f"{model}: {len(rows)}")
    for row in rows:
        print("  ", row["id"], *(row[label] for label in labels if row.get(label)))
    total += len(rows)
print(f"Total: {total}")
