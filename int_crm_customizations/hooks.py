import logging

_logger = logging.getLogger(__name__)

STUDIO_FIELD = "x_studio_tax_exempt"


def post_init_hook(env):
    """Carry the Studio tick over. Leads stay unapproved, and reasons and documents stay blank."""
    for model_name in ("res.partner", "crm.lead"):
        model = env[model_name].with_context(active_test=False, tracking_disable=True)
        field = model._fields.get(STUDIO_FIELD)
        if not field or field.type != "boolean":
            _logger.info("Tax exemption: %s has no %s to copy.", model_name, STUDIO_FIELD)
            continue
        records = model.search([(STUDIO_FIELD, "=", True)])
        records.write({"x_is_tax_exempt": True})
        _logger.info("Tax exemption: copied %s ticks on %s.", len(records), model_name)
