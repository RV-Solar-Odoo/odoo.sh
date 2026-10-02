"""Apply the carrier-neutral checkout tiers to existing databases.

The carrier xmlids were created from a noupdate file, so Odoo skips them on
every upgrade, including from non-noupdate data files. Write the values here.
"""

from odoo import SUPERUSER_ID, api

CARRIERS = {
    "delivery_carrier_shippo": {"is_published": False},
    "delivery_carrier_shippo_ups": {"is_published": False},
    "delivery_carrier_shippo_usps": {"is_published": False},
    "delivery_carrier_shippo_fedex": {"is_published": False},
    "delivery_carrier_shippo_ups_ground_saver": {"is_published": False},
    "delivery_carrier_shippo_ups_ground": {
        "name": "Ground Shipping",
        "int_shippo_provider": "UPS,FedEx",
        "int_shippo_service_include": "ground,home delivery",
        "int_shippo_service_exclude": "saver,surepost,smart post,smartpost,economy",
        "int_free_over_amount": 250.0,
        "is_published": True,
    },
    "delivery_carrier_shippo_ups_2day": {
        "name": "2 Day Shipping",
        "int_shippo_provider": "UPS,FedEx",
        "int_shippo_service_include": "2nd day,2 day,second day",
        "is_published": True,
    },
    "delivery_carrier_shippo_ups_overnight": {
        "name": "Overnight Shipping",
        "int_shippo_provider": "UPS,FedEx",
        "int_shippo_service_include": "next day,overnight",
        "is_published": True,
    },
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, vals in CARRIERS.items():
        carrier = env.ref(f"int_shippo_customizations.{xmlid}", raise_if_not_found=False)
        if carrier:
            carrier.write(vals)
