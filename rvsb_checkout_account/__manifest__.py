{
    'name': 'RVSB Checkout Account',
    'version': '19.0.1.0.0',
    'summary': 'Guests can ask for an account at checkout; it is activated from an emailed link.',
    'category': 'Website/Website',
    'depends': ['website_sale', 'auth_signup'],
    'data': [
        'data/mail_template.xml',
        'views/templates.xml',
        'views/sale_order_views.xml',
    ],
    'author': 'RV Solar & Battery',
    'license': 'LGPL-3',
}
