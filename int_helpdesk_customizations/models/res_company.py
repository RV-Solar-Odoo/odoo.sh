import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command

_logger = logging.getLogger(__name__)

_HELP_TEAM_WARNED = set()

TAG_FIELDS = (
    "int_help_tag_return_id",
    "int_help_tag_warranty_id",
    "int_help_tag_feedback_id",
    "int_help_tag_part_id",
)

TAG_XMLIDS = {
    "int_help_tag_return_id": "int_helpdesk_customizations.tag_help_return",
    "int_help_tag_warranty_id": "int_helpdesk_customizations.tag_help_warranty",
    "int_help_tag_feedback_id": "int_helpdesk_customizations.tag_help_feedback",
    "int_help_tag_part_id": "int_helpdesk_customizations.tag_help_part",
}

ALERTS = (
    ("help_return", "Returns"),
    ("help_warranty", "Warranty claims"),
    ("help_feedback", "Feedback"),
    ("help_part", "Part requests"),
)


class ResCompany(models.Model):
    _inherit = "res.company"

    int_help_team_id = fields.Many2one(
        "helpdesk.team",
        string="Help & Feedback team",
        ondelete="set null",
        help="Dealer Help & Feedback tickets are created on this team.",
    )
    int_help_tag_return_id = fields.Many2one(
        "helpdesk.tag",
        string="Return tag",
        ondelete="set null",
    )
    int_help_tag_warranty_id = fields.Many2one(
        "helpdesk.tag",
        string="Warranty tag",
        ondelete="set null",
    )
    int_help_tag_feedback_id = fields.Many2one(
        "helpdesk.tag",
        string="Feedback tag",
        ondelete="set null",
    )
    int_help_tag_part_id = fields.Many2one(
        "helpdesk.tag",
        string="Part request tag",
        ondelete="set null",
    )

    @api.constrains("int_help_team_id")
    def _check_int_help_team_company(self):
        for company in self:
            team = company.int_help_team_id
            if team and team.company_id and team.company_id != company:
                raise ValidationError(_("The Help & Feedback team must belong to this company."))

    def _int_help_team_or_warn(self):
        """The configured team, or an empty recordset. Warn once per company when it is missing."""
        self.ensure_one()
        team = self.sudo().int_help_team_id
        if team:
            _HELP_TEAM_WARNED.discard(self.id)
            return team
        if self.id not in _HELP_TEAM_WARNED:
            _HELP_TEAM_WARNED.add(self.id)
            _logger.warning(
                "Help & Feedback is hidden for %s because no helpdesk team is configured.",
                self.display_name,
            )
        return self.env["helpdesk.team"]

    def _int_help_tags(self):
        """The four kind tags configured here, plus the module's own tag records."""
        self.ensure_one()
        tags = self.env["helpdesk.tag"]
        company = self.sudo()
        for field_name in TAG_FIELDS:
            tags |= company[field_name]
        for xmlid in TAG_XMLIDS.values():
            tag = self.env.ref(xmlid, raise_if_not_found=False)
            if tag:
                tags |= tag
        return tags

    def _int_help_team_member(self):
        """An internal user who can be the first member of a new Dealer Support team."""
        self.ensure_one()
        user = self.env.user
        if user.active and not user.share and user.has_group("base.group_user"):
            return user
        return self.env["res.users"].search([
            ("active", "=", True),
            ("share", "=", False),
            ("company_ids", "in", self.id),
        ], limit=1, order="id")

    def _int_help_setup(self):
        """Fill a missing team, the four tags, and the four alert lists. Do not overwrite staff picks."""
        Alert = self.env["int.helpdesk.alert.list"].sudo()
        Team = self.env["helpdesk.team"].sudo()
        for company in self:
            if not company.int_help_team_id:
                member = company._int_help_team_member()
                if not member:
                    _logger.warning(
                        "Help & Feedback: no internal user to own Dealer Support for %s.",
                        company.display_name,
                    )
                else:
                    team = Team.with_company(company).with_context(
                        mail_create_nosubscribe=True,
                        tracking_disable=True,
                    ).create({
                        "name": "Dealer Support",
                        "company_id": company.id,
                        "member_ids": [Command.set(member.ids)],
                    })
                    company.int_help_team_id = team
            for field_name, xmlid in TAG_XMLIDS.items():
                if company[field_name]:
                    continue
                tag = self.env.ref(xmlid, raise_if_not_found=False)
                if tag:
                    company[field_name] = tag
            for code, name in ALERTS:
                existing = Alert.search([
                    ("code", "=", code),
                    ("company_id", "=", company.id),
                ], limit=1)
                if existing:
                    continue
                Alert.create({
                    "name": name,
                    "code": code,
                    "company_id": company.id,
                })
