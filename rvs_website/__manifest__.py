{
    'name': "RV Solar Website",
    'version': "19.0.1.0.0",
    'category': "Website",
    'summary': "RV Solar website styling and frontend customizations",
    'depends': ['website'],
    'assets': {
        'web.assets_frontend': [
            'rvs_website/static/src/scss/website.scss',
        ],
    },
    'installable': True,
    'application': False,
}
