{
    "name": "Documents Customizations",
    "version": "19.0.1.0.2",
    "category": "Productivity/Documents",
    "summary": "Opens the staff SOPs from Sales, Inventory, and Barcode",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["documents", "sale", "stock_barcode"],
    "application": False,
    "data": [
        "data/sop_documents.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "int_documents_customizations/static/src/sop_help.scss",
            "int_documents_customizations/static/src/sop_help.xml",
            "int_documents_customizations/static/src/sop_help.js",
        ],
    },
}
