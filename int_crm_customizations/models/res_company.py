from odoo import fields, models

from .dealer_certificate import DEFAULT_REMINDER_DAYS


class ResCompany(models.Model):
    _inherit = "res.company"

    int_cert_reminder_days = fields.Char(
        string="Certificate Reminders",
        default=DEFAULT_REMINDER_DAYS,
        help="Days before a dealer certificate expires to email the dealer, separated by commas.",
    )
    int_cert_reviewer_id = fields.Many2one(
        "res.users",
        string="Certificate Reviewer",
        domain=[("share", "=", False)],
        help="Reviews certificates dealers upload when the dealer has no salesperson.",
    )

    def _int_cert_reminder_days(self):
        """The reminder thresholds as whole days, largest first."""
        self.ensure_one()
        days = {int(day) for day in (self.int_cert_reminder_days or "").split(",") if day.strip().isdigit()}
        days.discard(0)
        return sorted(days, reverse=True)
