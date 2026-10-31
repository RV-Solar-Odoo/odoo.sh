"""Publish a UPS and a FedEx method for each checkout speed.

The carrier xmlids were created from a noupdate file, so the data file does
not update the existing Ground / 2 Day / Overnight methods. New FedEx records
load from that file; this writes both sets so an upgrade lands on six methods.
"""

from odoo import SUPERUSER_ID, api

CARRIERS = {
    "delivery_carrier_shippo_ups_ground": {
        "name": "UPS Ground",
        "int_shippo_provider": "UPS",
        "int_shippo_service_include": "ground,home delivery",
        "int_shippo_service_exclude": "saver,surepost,smart post,smartpost,economy",
        "int_free_over_amount": 250.0,
        "sequence": 21,
        "is_published": True,
    },
    "delivery_carrier_shippo_fedex_ground": {
        "name": "FedEx Ground",
        "int_shippo_provider": "FedEx",
        "int_shippo_service_include": "ground,home delivery",
        "int_shippo_service_exclude": "saver,surepost,smart post,smartpost,economy",
        "int_free_over_amount": 250.0,
        "sequence": 22,
        "is_published": True,
    },
    "delivery_carrier_shippo_ups_2day": {
        "name": "UPS 2 Day",
        "int_shippo_provider": "UPS",
        "int_shippo_service_include": "2nd day,2 day,2day,second day",
        "int_shippo_service_exclude": False,
        "int_free_over_amount": 0.0,
        "sequence": 23,
        "is_published": True,
    },
    "delivery_carrier_shippo_fedex_2day": {
        "name": "FedEx 2 Day",
        "int_shippo_provider": "FedEx",
        "int_shippo_service_include": "2nd day,2 day,2day,second day",
        "int_shippo_service_exclude": False,
        "int_free_over_amount": 0.0,
        "sequence": 24,
        "is_published": True,
    },
    "delivery_carrier_shippo_ups_overnight": {
        "name": "UPS Overnight",
        "int_shippo_provider": "UPS",
        "int_shippo_service_include": "next day,overnight",
        "int_shippo_service_exclude": False,
        "int_free_over_amount": 0.0,
        "sequence": 25,
        "is_published": True,
    },
    "delivery_carrier_shippo_fedex_overnight": {
        "name": "FedEx Overnight",
        "int_shippo_provider": "FedEx",
        "int_shippo_service_include": "next day,overnight",
        "int_shippo_service_exclude": False,
        "int_free_over_amount": 0.0,
        "sequence": 26,
        "is_published": True,
    },
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    product = env.ref("int_shippo_customizations.product_product_delivery_shippo")
    for xmlid, vals in CARRIERS.items():
        carrier = env.ref(f"int_shippo_customizations.{xmlid}", raise_if_not_found=False)
        if carrier:
            carrier.write(vals)
            continue
        carrier = env["delivery.carrier"].create({
            **vals,
            "delivery_type": "shippo",
            "integration_level": "rate",
            "product_id": product.id,
        })
        env["ir.model.data"]._update_xmlids([{
            "xml_id": f"int_shippo_customizations.{xmlid}",
            "record": carrier,
            "noupdate": True,
        }])
