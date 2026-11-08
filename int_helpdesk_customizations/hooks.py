def post_init_hook(env):
    """Point Help & Feedback at existing teams, and fill tags and alert lists."""
    env["res.company"].with_context(active_test=False).search([])._int_help_setup()
