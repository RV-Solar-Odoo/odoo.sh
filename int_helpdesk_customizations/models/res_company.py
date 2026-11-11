import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

_HELP_TEAM_WARNED = set()

TAG_FIELDS = (
    "int_help_tag_return_id",
    "int_help_tag_warranty_id",
    "int_help_tag_feedback_id",
    "int_help_tag_part_id",
    "int_help_tag_general_id",
)

# Kind -> company field. Returns and warranty use the existing returns team.
# Feedback and part requests use the existing general-inquiries team.
# Nothing here creates a team.
TEAM_FIELDS = {
    "return": "int_help_team_return_id",
    "warranty": "int_help_team_warranty_id",
    "feedback": "int_help_team_feedback_id",
    "part": "int_help_team_part_id",
    "general": "int_help_team_general_id",
}
TEAM_NAME_HINTS = {
    "int_help_team_return_id": ("return",),
    "int_help_team_warranty_id": ("return",),
    "int_help_team_feedback_id": ("inquir", "general"),
    "int_help_team_part_id": ("inquir", "general"),
    "int_help_team_general_id": ("inquir", "general"),
}

TAG_XMLIDS = {
    "int_help_tag_return_id": "int_helpdesk_customizations.tag_help_return",
    "int_help_tag_warranty_id": "int_helpdesk_customizations.tag_help_warranty",
    "int_help_tag_feedback_id": "int_helpdesk_customizations.tag_help_feedback",
    "int_help_tag_part_id": "int_helpdesk_customizations.tag_help_part",
    "int_help_tag_general_id": "int_helpdesk_customizations.tag_help_general",
}

ALERTS = (
    ("help_return", "Returns"),
    ("help_warranty", "Warranty claims"),
    ("help_feedback", "Feedback"),
    ("help_part", "Part requests"),
    ("help_general", "General inquiries"),
)


class ResCompany(models.Model):
    _inherit = "res.company"

    int_help_team_return_id = fields.Many2one(
        "helpdesk.team",
        string="Returns team",
        ondelete="set null",
        help="Return requests are created on this existing team.",
    )
    int_help_team_warranty_id = fields.Many2one(
        "helpdesk.team",
        string="Warranty team",
        ondelete="set null",
        help="Warranty claims are created on this existing team. That is the returns team.",
    )
    int_help_team_feedback_id = fields.Many2one(
        "helpdesk.team",
        string="Feedback team",
        ondelete="set null",
        help="Feedback is created on this existing team.",
    )
    int_help_team_part_id = fields.Many2one(
        "helpdesk.team",
        string="Part request team",
        ondelete="set null",
        help="Part requests are created on this existing team.",
    )
    int_help_team_general_id = fields.Many2one(
        "helpdesk.team",
        string="General inquiries team",
        ondelete="set null",
        help="General inquiries are created on this existing team.",
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
    int_help_tag_general_id = fields.Many2one(
        "helpdesk.tag",
        string="General inquiry tag",
        ondelete="set null",
    )

    @api.constrains(*TEAM_FIELDS.values())
    def _check_int_help_team_company(self):
        for company in self:
            for field_name in TEAM_FIELDS.values():
                team = company[field_name]
                if team and team.company_id and team.company_id != company:
                    raise ValidationError(_("The Help & Feedback team must belong to this company."))

    def _int_help_team_for(self, kind):
        """The existing team for this kind, or an empty recordset."""
        self.ensure_one()
        field_name = TEAM_FIELDS.get(kind)
        team = self.sudo()[field_name] if field_name else self.env["helpdesk.team"]
        return team or self.env["helpdesk.team"]

    def _int_help_ready(self):
        """True when every kind has an existing team. Warn once when one is missing."""
        self.ensure_one()
        company = self.sudo()
        missing = [
            field_name for field_name in TEAM_FIELDS.values() if not company[field_name]
        ]
        if not missing:
            _HELP_TEAM_WARNED.discard(self.id)
            return True
        if self.id not in _HELP_TEAM_WARNED:
            _HELP_TEAM_WARNED.add(self.id)
            _logger.warning(
                "Help & Feedback is hidden for %s because these teams are not set: %s.",
                self.display_name,
                ", ".join(missing),
            )
        return False

    def _int_help_find_team(self, hints):
        """An existing team for this company whose name matches one of the hints."""
        self.ensure_one()
        teams = self.env["helpdesk.team"].sudo().search([
            ("company_id", "=", self.id),
        ])
        for hint in hints:
            match = teams.filtered(lambda team, hint=hint: hint in (team.name or "").lower())
            if match:
                return match.sorted("id")[:1]
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

    def _int_help_setup(self):
        """Point empty kind fields at existing teams, and fill tags and alert lists.

        Does not create a helpdesk team and does not overwrite a team someone already chose.
        """
        Alert = self.env["int.helpdesk.alert.list"].sudo()
        for company in self:
            for field_name, hints in TEAM_NAME_HINTS.items():
                if company[field_name]:
                    continue
                team = company._int_help_find_team(hints)
                if team:
                    company[field_name] = team
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
            company._int_help_archive_unused_dealer_support()

    @api.model
    def _int_help_setup_all(self):
        """Run on every module update, so a new request type gets its team, tag and alert list."""
        self.with_context(active_test=False).search([])._int_help_setup()

    def _int_help_archive_unused_dealer_support(self):
        """Hide an empty team this module used to create. Leave it if it already has tickets."""
        self.ensure_one()
        Team = self.env["helpdesk.team"].sudo()
        if "active" not in Team._fields:
            return
        teams = Team.with_context(active_test=False).search([
            ("company_id", "=", self.id),
            ("name", "=", "Dealer Support"),
            ("active", "=", True),
        ])
        Ticket = self.env["helpdesk.ticket"].sudo()
        for team in teams:
            if Ticket.search_count([("team_id", "=", team.id)]):
                continue
            team.active = False
