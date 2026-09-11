{
    "name": "Inventory Customizations",
    "version": "19.0.2.4.0",
    "category": "Inventory/Inventory",
    "summary": "Adds RVSB product fields, form layout, and battery Ground shipping rules",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["product", "stock", "purchase", "stock_delivery"],
    "application": False,
    "data": [
        "data/product_category_data.xml",
        "data/product_category_shipping.xml",
        "views/product_category_views.xml",
        "views/product_template_views.xml",
    ],
}
