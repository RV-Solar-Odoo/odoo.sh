from . import models
from . import wizard


def post_init_hook(env):
    from .hooks import ensure_package_types
    ensure_package_types(env)
