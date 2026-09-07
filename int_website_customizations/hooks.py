def unpublish_standard_delivery(env):
    configure_checkout_shipping(env)


def configure_checkout_shipping(env):
    env["delivery.carrier"].search([
        ("is_published", "=", True),
        ("name", "ilike", "standard delivery"),
    ]).write({"is_published": False})
    free = env.ref("int_website_customizations.delivery_carrier_free_250", raise_if_not_found=False)
    if free:
        free.write({"is_published": False})
