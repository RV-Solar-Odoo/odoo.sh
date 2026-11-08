from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    int_help_team_id = fields.Many2one(
        related="company_id.int_help_team_id",
        readonly=False,
        string="Help & Feedback team",
        domain="[('company_id', '=', company_id)]",
    )
    int_help_tag_return_id = fields.Many2one(
        related="company_id.int_help_tag_return_id",
        readonly=False,
        string="Return tag",
    )
    int_help_tag_warranty_id = fields.Many2one(
        related="company_id.int_help_tag_warranty_id",
        readonly=False,
        string="Warranty tag",
    )
    int_help_tag_feedback_id = fields.Many2one(
        related="company_id.int_help_tag_feedback_id",
        readonly=False,
        string="Feedback tag",
    )
    int_help_tag_part_id = fields.Many2one(
        related="company_id.int_help_tag_part_id",
        readonly=False,
        string="Part request tag",
    )
