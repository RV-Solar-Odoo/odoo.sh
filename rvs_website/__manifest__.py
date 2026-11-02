{
    'name': "RV Solar Website",
    'version': "19.0.1.4.3",
    'category': "Website",
    'summary': "RV Solar website styling and frontend customizations",
    'author': "Internal",
    'license': "LGPL-3",
    'depends': ['website'],
    'data': [
        'views/templates.xml',
        'views/about_us.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'rvs_website/static/src/scss/website.scss',
        ],
    },
    'installable': True,
    'application': False,
}
