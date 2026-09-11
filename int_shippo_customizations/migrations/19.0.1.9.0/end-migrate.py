"""Remove the Small/Medium/Large Carton package types seeded in 19.0.1.1.0.

Shippo rates are quoted from ``int.shippo.box`` records now, so these
``stock.package.type`` rows are unused. The model has no ``active`` field, so
they are deleted; the only reference to them (``stock.quant.package``) is
``ondelete='set null'``.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# (xmlid, name, sequence_code) as created by the old ensure_package_types hook.
SEEDED_BOXES = [
    ("int_shippo_box_small", "Small Carton", "SML"),
    ("int_shippo_box_medium", "Medium Carton", "MED"),
    ("int_shippo_box_large", "Large Carton", "LRG"),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    PackageType = env["stock.package.type"].sudo()
    to_delete = PackageType.browse()

    for xmlid, name, sequence_code in SEEDED_BOXES:
        record = env.ref(f"int_shippo_customizations.{xmlid}", raise_if_not_found=False)
        if record and record.exists():
            to_delete |= record
            continue
        # xmlid link lost: fall back to the exact fingerprint of the seeded row.
        to_delete |= PackageType.search(
            [
                ("name", "=", name),
                ("sequence_code", "=", sequence_code),
                ("package_use", "=", "disposable"),
            ]
        )

    if not to_delete:
        return

    _logger.info("Removing seeded Shippo carton package types: %s", to_delete.mapped("name"))
    to_delete.unlink()
