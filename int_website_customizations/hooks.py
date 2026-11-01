def unpublish_standard_delivery(env):
    configure_checkout_shipping(env)
    show_payment_brand_on_receipt(env)
    ensure_google_places_parameter(env)


def ensure_google_places_parameter(env):
    """Show the key in System Parameters before anyone opens Website settings."""
    icp = env["ir.config_parameter"].sudo()
    key = "int_website.google_places_api_key"
    if not icp.search([("key", "=", key)], limit=1):
        icp.set_param(key, "")


def disable_customer_invoice_email(env):
    """Keep Automatic Invoice off. That setting emails the retail customer.

    Paid website orders are invoiced from the payment, and the invoice is not sent.
    """
    env["ir.config_parameter"].sudo().set_param("sale.automatic_invoice", "False")


def show_payment_brand_on_receipt(env):
    """Print Visa or Bank transfer on the checkout receipt, not the provider name."""
    marker = "Payment Method:"
    insert = '<t t-out="object._int_receipt_payment_method(tx_sudo)"/>'
    templates = env["mail.template"].sudo().search([
        ("model", "=", "sale.order"),
        ("body_html", "ilike", marker),
    ])
    for template in templates:
        html = str(template.body_html or "")
        if "_int_receipt_payment_method" in html:
            continue
        start = html.find(marker)
        span_end = html.find("</span>", start)
        amount = html.find("format_amount(tx_sudo.amount", start)
        paren = html.rfind("(", span_end, amount) if span_end >= 0 and amount >= 0 else -1
        if paren < 0:
            continue
        template.body_html = (
            html[:span_end + len("</span>")]
            + "\n                    "
            + insert
            + "\n                    "
            + html[paren:]
        )


def configure_checkout_shipping(env):
    env["delivery.carrier"].search([
        ("is_published", "=", True),
        ("name", "ilike", "standard delivery"),
    ]).write({"is_published": False})
    free = env.ref("int_website_customizations.delivery_carrier_free_250", raise_if_not_found=False)
    if free:
        free.write({"is_published": False})
