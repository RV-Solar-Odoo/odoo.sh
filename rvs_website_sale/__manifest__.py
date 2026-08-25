{
    'name': "RV Solar Website Sale",
    'version': "19.0.1.0.0",
    'category': "Website",
    'summary': "Adds a product data sheet download button to the website product page",
    'depends': ['website_sale'],
    'data': [
        'views/product_template_views.xml',
        'views/product_template_website.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'rvs_website_sale/static/src/scss/product_data_sheet.scss',
        ],
    },
    'installable': True,
    'application': False,
}
