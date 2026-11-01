import base64
import hashlib
from pathlib import Path

from odoo import api, fields, models

SOP_DIR = Path(__file__).resolve().parent.parent / "data" / "sops"

# Filenames are the document names in the SOPs folder. Apps are menu xmlids.
SOPS = (
    {
        "key": "website_orders",
        "filename": "Website orders.pdf",
        "sequence": 10,
        "apps": "sale.sale_menu_root",
    },
    {
        "key": "orders_by_hand",
        "filename": "Orders entered by hand.pdf",
        "sequence": 20,
        "apps": "sale.sale_menu_root",
    },
    {
        "key": "receiving_barcodes",
        "filename": "Receiving with barcodes.pdf",
        "sequence": 10,
        "apps": "stock.menu_stock_root,stock_barcode.stock_barcode_menu",
    },
    {
        "key": "fulfillment_pick_ship",
        "filename": "Fulfillment pick and ship.pdf",
        "sequence": 20,
        "apps": "stock.menu_stock_root,stock_barcode.stock_barcode_menu",
    },
)


class DocumentsDocument(models.Model):
    _inherit = "documents.document"

    int_sop_key = fields.Char(string="SOP key", copy=False, index=True)
    int_sop_apps = fields.Char(string="SOP apps")
    int_sop_sequence = fields.Integer(string="SOP sequence")

    @api.model
    def _int_ensure_sop_documents(self):
        """Create or refresh the staff SOPs in the shared SOPs folder.

        Runs on install and on every upgrade. An SOP already in that folder
        under the same name is reused, so a file uploaded before this module
        is installed is not duplicated.
        """
        folder = self.search(
            [
                ("name", "=", "SOPs"),
                ("type", "=", "folder"),
                ("folder_id", "=", False),
            ],
            order="id",
            limit=1,
        )
        if not folder:
            folder = self.create(
                {
                    "name": "SOPs",
                    "type": "folder",
                    "access_internal": "view",
                    "access_via_link": "none",
                    "company_id": False,
                }
            )
        for spec in SOPS:
            path = SOP_DIR / spec["filename"]
            raw = path.read_bytes()
            checksum = hashlib.sha1(raw).hexdigest()
            document = self.search(
                [("int_sop_key", "=", spec["key"]), ("type", "=", "binary")],
                limit=1,
            )
            if not document:
                document = self.search(
                    [
                        ("name", "=", spec["filename"]),
                        ("folder_id", "=", folder.id),
                        ("type", "=", "binary"),
                    ],
                    order="id",
                    limit=1,
                )
            values = {
                "name": spec["filename"],
                "folder_id": folder.id,
                "type": "binary",
                "access_internal": "view",
                "access_via_link": "none",
                "company_id": False,
                "int_sop_key": spec["key"],
                "int_sop_apps": spec["apps"],
                "int_sop_sequence": spec["sequence"],
            }
            if not document or document.checksum != checksum:
                values["datas"] = base64.b64encode(raw).decode()
            if document:
                document.write(values)
            else:
                self.create(values)

    @api.model
    def int_sop_links(self, app_xmlid):
        """SOPs for one app, in menu order. Each url opens that document."""
        app_xmlid = (app_xmlid or "").strip()
        if not app_xmlid:
            return []
        documents = self.search(
            [("int_sop_key", "!=", False)],
            order="int_sop_sequence, id",
        )
        links = []
        for document in documents:
            apps = [
                item.strip()
                for item in (document.int_sop_apps or "").split(",")
                if item.strip()
            ]
            if app_xmlid not in apps or not document.access_url:
                continue
            label = document.name or ""
            for suffix in (".docx", ".pdf"):
                if label.lower().endswith(suffix):
                    label = label[: -len(suffix)]
                    break
            links.append(
                {
                    "id": document.id,
                    "label": label,
                    "url": document.access_url,
                }
            )
        return links
