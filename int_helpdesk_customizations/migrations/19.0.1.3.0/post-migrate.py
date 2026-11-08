"""Point Help & Feedback at the teams that already exist."""

from odoo import SUPERUSER_ID, api

from odoo.addons.int_helpdesk_customizations.hooks import post_init_hook


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    post_init_hook(env)
