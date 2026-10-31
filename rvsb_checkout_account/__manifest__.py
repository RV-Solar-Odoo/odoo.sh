{
    'name': 'RVSB Checkout Account',
    'version': '19.0.1.1.0',
    'summary': 'Guests can ask for an account on the order confirmation page; it is activated from an emailed link.',
    'category': 'Website/Website',
    'depends': ['website_sale', 'auth_signup'],
    'data': [
        'data/mail_template.xml',
        'views/templates.xml',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'rvsb_checkout_account/static/src/interactions/account_cta.js',
        ],
    },
    'author': 'RV Solar & Battery',
    'license': 'LGPL-3',
}
