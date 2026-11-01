{
    "name": "Web Customizations",
    "summary": "Black and gray backend with Nomadiq blue accents and the Nomadiq logo in the top bar",
    "description": """
Re-colors the Odoo back office:

* Near-black top bar with the Nomadiq wordmark, light-gray menu text and blue badges
* Nomadiq blue (#3a4efd, same as the website) for primary buttons, links, checkboxes,
  focused inputs, selected rows, active filters and the active tab
* Charcoal highlight for the current pipeline step
* Everything else stays light gray and white so lists and forms read like stock Odoo

Colors live at the top of static/src/scss/primary_variables.scss and
static/src/scss/theme.scss. Uninstalling returns the stock look.
""",
    "version": "19.0.1.0.0",
    "category": "Themes/Backend",
    "author": "Internal",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise"],
    "assets": {
        # Prepended so these values are set before every !default in web and web_enterprise.
        # This file must use literal values only. Nothing from Odoo exists yet.
        "web._assets_primary_variables": [
            ("prepend", "int_web_customizations/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_backend": [
            "int_web_customizations/static/src/scss/theme.scss",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": False,
}
