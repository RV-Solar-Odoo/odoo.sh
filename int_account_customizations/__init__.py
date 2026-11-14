from . import controllers
from . import models


def post_init_hook(env):
    threshold = env["int.nexus.threshold"]
    threshold.seed_defaults()
    threshold.mark_sale_treatments()
    threshold.assign_default_recipient()
    threshold.schedule_monthly_check()
