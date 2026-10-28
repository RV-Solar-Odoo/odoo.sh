# Part of the Nomadiq Odoo customizations.
{
    'name': 'eCommerce Tag Groups',
    'summary': 'Group product tags into labeled filter sections on the shop page',
    'description': """
Adds a "Tag Group" model and a group field on product tags. On the /shop
sidebar (desktop and mobile), tags are rendered one section per group, each
with its own heading, collapse state and display style (checkboxes or
dropdown). Filtering is AND across groups and OR within a group.
""",
    'version': '19.0.1.4.0',
    'category': 'Website/Website',
    'author': 'Nomadiq',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_tag_group_views.xml',
        'views/product_tag_views.xml',
        'views/website_sale_menus.xml',
        'views/templates.xml',
    ],
    'installable': True,
    'application': False,
}
