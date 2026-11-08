def post_init_hook(env):
    """Create the Dealer Support team, tags, and alert lists for every company."""
    env["res.company"].with_context(active_test=False).search([])._int_help_setup()
