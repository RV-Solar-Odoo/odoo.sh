from . import models


def post_init_hook(env):
    from .hooks import unpublish_standard_delivery
    unpublish_standard_delivery(env)

