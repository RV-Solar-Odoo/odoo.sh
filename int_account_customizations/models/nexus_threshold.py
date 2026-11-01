import calendar
import logging
from datetime import date

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.tools.misc import formatLang

from ..data.nexus_defaults import DEFAULTS

_logger = logging.getLogger(__name__)

ANNIE_LOGIN = "anniekingme@gmail.com"


class NexusThreshold(models.Model):
    _name = "int.nexus.threshold"
    _description = "Sales tax threshold"
    _order = "state_id"

    state_id = fields.Many2one("res.country.state", required=True, ondelete="cascade")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    amount_threshold = fields.Monetary(
        string="Dollar amount",
        currency_field="currency_id",
        help="Untaxed sales shipped to this state. Zero means this state has no dollar test.",
    )
    transaction_threshold = fields.Integer(
        string="Transactions",
        help="Confirmed orders shipped to this state. Zero means this state has no transaction test.",
    )
    trigger = fields.Selection(
        [("or", "Either"), ("and", "Both")],
        required=True,
        default="or",
        help="Either: the email goes out when the dollars or the transaction count is crossed. "
             "Both: Connecticut and New York, where the two tests must be crossed together.",
    )
    period = fields.Selection(
        [
            ("either_year", "Current or previous calendar year"),
            ("current_year", "Current calendar year"),
            ("previous_year", "Previous calendar year"),
            ("trailing_12", "Past 12 months"),
            ("four_quarters", "Last four sales-tax quarters"),
            ("sept_30", "12 months ending September 30"),
        ],
        required=True,
        default="either_year",
    )
    note = fields.Char()
    alerted = fields.Boolean(
        string="Notified",
        readonly=True,
        help="Set when Annie has been emailed for the current crossing. "
             "Cleared on a later check if the state falls back under the threshold.",
    )
    last_amount = fields.Monetary(string="Latest sales", currency_field="currency_id", readonly=True)
    last_count = fields.Integer(string="Latest orders", readonly=True)
    last_window = fields.Char(string="Measured", readonly=True)
    count_taxable_goods = fields.Boolean(
        string="Taxable goods",
        default=True,
        help="Products that carry a sales tax, other than services.",
    )
    count_exempt_goods = fields.Boolean(
        string="Exempt goods",
        default=True,
        help="Products with no sales tax, other than services and wholesale.",
    )
    count_taxable_services = fields.Boolean(
        string="Taxable services",
        default=True,
        help="Services whose product has a sales tax. Delivery counts when the delivery product is taxed.",
    )
    count_exempt_services = fields.Boolean(
        string="Exempt services",
        default=True,
        help="Services with no sales tax, including delivery when it is not taxed.",
    )
    count_resale = fields.Boolean(
        string="Wholesale / resale",
        default=True,
        help="Goods on the wholesale fiscal position, or goods taxed as resale.",
    )
    count_marketplace = fields.Boolean(
        string="Marketplace collected",
        default=True,
        help="Orders marked as sold through a marketplace that collected the tax.",
    )
    exclude_returned = fields.Boolean(
        string="Leave out returns",
        help="Returned quantities are left out of the total.",
    )

    _state_company_uniq = models.Constraint(
        "unique(state_id, company_id)",
        "This state already has a threshold for this company.",
    )

    @api.model
    def seed_defaults(self):
        """Add a row per state for each US company. Leave rows that already exist."""
        companies = self.env["res.company"].search([
            "|",
            ("country_id.code", "=", "US"),
            ("account_fiscal_country_id.code", "=", "US"),
        ])
        if not companies:
            return
        states = {
            state.code: state
            for state in self.env["res.country.state"].search([("country_id.code", "=", "US")])
        }
        existing = {
            (row.company_id.id, row.state_id.id)
            for row in self.sudo().search([("company_id", "in", companies.ids)])
        }
        vals_list = []
        for company in companies:
            for row in DEFAULTS:
                state = states.get(row["code"])
                if not state or (company.id, state.id) in existing:
                    continue
                vals_list.append({
                    "state_id": state.id,
                    "company_id": company.id,
                    "amount_threshold": row["amount"],
                    "transaction_threshold": row["transactions"],
                    "trigger": row["trigger"],
                    "period": row["period"],
                    "note": row["note"],
                    "count_taxable_goods": row["taxable_goods"],
                    "count_exempt_goods": row["exempt_goods"],
                    "count_taxable_services": row["taxable_services"],
                    "count_exempt_services": row["exempt_services"],
                    "count_resale": row["resale"],
                    "count_marketplace": row["marketplace"],
                    "exclude_returned": row["exclude_returned"],
                })
        if vals_list:
            self.sudo().create(vals_list)

    @api.model
    def mark_sale_treatments(self):
        """Tag the wholesale position and the placeholder out-of-state tax."""
        taxes = self.env["account.tax"].sudo().search([("type_tax_use", "in", ("sale", "all"))])
        for tax in taxes:
            if tax.int_nexus_treatment != "normal":
                continue
            label = "%s %s" % (tax.name or "", tax.invoice_label or "")
            folded = label.lower()
            if "resale" in folded or "wholesale" in folded:
                tax.int_nexus_treatment = "resale"
            elif "out of state" in folded:
                tax.int_nexus_treatment = "not_collecting"
        positions = self.env["account.fiscal.position"].sudo().search([])
        for position in positions:
            if position.int_nexus_resale:
                continue
            name = (position.name or "").lower()
            if "wholesale" in name or "resale" in name:
                position.int_nexus_resale = True

    @api.model
    def assign_default_recipient(self):
        param = self.env["ir.config_parameter"].sudo()
        if param.get_param("int_account.nexus_alert_user_id"):
            return
        user = self.env["res.users"].sudo().search([("login", "=", ANNIE_LOGIN)], limit=1)
        if user:
            param.set_param("int_account.nexus_alert_user_id", str(user.id))

    @api.model
    def schedule_monthly_check(self):
        cron = self.env.ref("int_account_customizations.ir_cron_nexus_threshold", raise_if_not_found=False)
        if not cron:
            return
        now = fields.Datetime.now()
        first = now.replace(day=1, hour=15, minute=0, second=0, microsecond=0)
        if first <= now:
            first += relativedelta(months=1)
        cron.sudo().nextcall = first

    @api.model
    def cron_check_nexus(self):
        self.seed_defaults()
        today = self.env.context.get("int_nexus_today") or fields.Date.context_today(self)
        breaches = self._collect_breaches(fields.Date.to_date(today))
        if breaches:
            self._email_breaches(breaches)

    @api.model
    def _collect_breaches(self, today):
        """Measure every threshold and return the ones that newly crossed."""
        breaches = []
        thresholds = self.sudo().search([])
        for company in thresholds.company_id:
            company_rows = thresholds.filtered(lambda row: row.company_id == company)
            domestic_states = company.domestic_fiscal_position_id.state_ids
            windows = {}
            for period in set(company_rows.mapped("period")):
                windows[period] = [
                    (start, end, self._orders_between(company, start, end))
                    for start, end in self._period_windows(period, today)
                ]
            for row in company_rows:
                hit = None
                watched = None
                for start, end, orders in windows[row.period]:
                    amount, count = row._measure(orders)
                    over, amount_hit, count_hit = row._is_over(amount, count)
                    candidate = {
                        "start": start,
                        "end": end,
                        "amount": amount,
                        "count": count,
                        "amount_hit": amount_hit,
                        "count_hit": count_hit,
                    }
                    if watched is None or figures["amount"] > watched["amount"]:
                        watched = candidate
                    if over and hit is None:
                        hit = candidate
                shown = hit or watched
                row.write({
                    "last_amount": shown["amount"] if shown else 0.0,
                    "last_count": shown["count"] if shown else 0,
                    "last_window": self._format_window(shown["start"], shown["end"]) if shown else False,
                })
                if row.state_id in domestic_states:
                    if row.alerted:
                        row.alerted = False
                    continue
                if hit and not row.alerted:
                    row.alerted = True
                    breaches.append((row, hit))
                elif not hit and row.alerted:
                    row.alerted = False
        return breaches

    def _is_over(self, amount, count):
        self.ensure_one()
        amount_hit = bool(self.amount_threshold) and amount >= self.amount_threshold
        count_hit = bool(self.transaction_threshold) and count >= self.transaction_threshold
        if self.trigger == "and":
            return bool(amount_hit and count_hit), amount_hit, count_hit
        return bool(amount_hit or count_hit), amount_hit, count_hit

    @api.model
    def _period_windows(self, period, today):
        if period == "either_year":
            return [
                (date(today.year, 1, 1), today),
                (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)),
            ]
        if period == "current_year":
            return [(date(today.year, 1, 1), today)]
        if period == "previous_year":
            return [(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))]
        if period == "trailing_12":
            return [(today - relativedelta(months=12), today)]
        if period == "sept_30":
            end_year = today.year if (today.month, today.day) >= (9, 30) else today.year - 1
            end = date(end_year, 9, 30)
            return [(date(end.year - 1, 10, 1), end)]
        end = self._last_completed_quarter_end(today)
        return [(end - relativedelta(months=12) + relativedelta(days=1), end)]

    @api.model
    def _last_completed_quarter_end(self, today):
        """New York sales-tax quarters end on the last day of February, May, August, and November."""
        candidates = []
        for year in (today.year - 1, today.year):
            for month in (2, 5, 8, 11):
                end = date(year, month, calendar.monthrange(year, month)[1])
                if end < today:
                    candidates.append(end)
        return max(candidates)

    @api.model
    def _orders_between(self, company, start, end):
        start_dt = fields.Datetime.to_datetime(start)
        end_dt = fields.Datetime.to_datetime(end + relativedelta(days=1))
        orders = self.env["sale.order"].sudo().search([
            ("company_id", "=", company.id),
            ("state", "in", ("sale", "done")),
            ("date_order", ">=", start_dt),
            ("date_order", "<", end_dt),
        ])
        orders.mapped("order_line.product_id.taxes_id")
        orders.mapped("order_line.tax_ids")
        orders.mapped("fiscal_position_id")
        return orders

    def _measure(self, orders):
        """Untaxed total and order count for this state's include rules."""
        self.ensure_one()
        amount = 0.0
        count = 0
        company = self.company_id
        state_orders = orders.filtered(
            lambda order: order.partner_shipping_id.state_id == self.state_id
        )
        for order in state_orders:
            if order.int_marketplace_collected and not self.count_marketplace:
                continue
            included = 0.0
            counted = False
            for line in order.order_line:
                portion = self._line_amount(line, company)
                if portion is None:
                    continue
                included += portion
                counted = True
            if not counted:
                continue
            amount += included
            count += 1
        return amount, count

    def _line_amount(self, line, company):
        """Company-currency untaxed amount, or None when this state skips the line."""
        if line.display_type or not line.product_id:
            return None
        if not self._line_counts(line, company):
            return None
        ordered = line.product_uom_qty
        returned = line.qty_returned if "qty_returned" in line._fields else 0.0
        ratio = self._kept_ratio(ordered, returned)
        if self.exclude_returned and ordered and ratio <= 0:
            return None
        order = line.order_id
        return order.currency_id._convert(
            line.price_subtotal * ratio,
            company.currency_id,
            company,
            fields.Date.to_date(order.date_order),
        )

    def _line_counts(self, line, company):
        if self._is_service(line):
            taxed = self._product_is_taxable(line.product_id, company)
            return self.count_taxable_services if taxed else self.count_exempt_services
        if self._is_resale(line):
            return self.count_resale
        taxed = self._product_is_taxable(line.product_id, company)
        return self.count_taxable_goods if taxed else self.count_exempt_goods

    def _kept_ratio(self, ordered, returned):
        if not self.exclude_returned or not ordered:
            return 1.0
        return max(ordered - returned, 0.0) / ordered

    def _is_service(self, line):
        if "is_delivery" in line._fields and line.is_delivery:
            return True
        return line.product_id.type == "service"

    def _is_resale(self, line):
        position = line.order_id.fiscal_position_id
        if position and position.int_nexus_resale:
            return True
        return any(tax.int_nexus_treatment == "resale" for tax in line.tax_ids)

    def _product_is_taxable(self, product, company):
        taxes = product.with_company(company).taxes_id
        return any(
            tax.type_tax_use in ("sale", "all") and tax.amount_type != "group" and tax.amount
            for tax in taxes
        )

    @api.model
    def _format_window(self, start, end):
        return "%s %s, %s – %s %s, %s" % (
            start.strftime("%B"), start.day, start.year,
            end.strftime("%B"), end.day, end.year,
        )

    @api.model
    def _email_breaches(self, breaches):
        param = self.env["ir.config_parameter"].sudo().get_param("int_account.nexus_alert_user_id")
        try:
            user_id = int(param)
        except (TypeError, ValueError):
            user_id = 0
        user = self.env["res.users"].sudo().browse(user_id)
        if not user or not user.email:
            _logger.warning("A sales tax threshold was crossed but no recipient email is set.")
            return
        names = [row.state_id.name for row, _hit in breaches]
        if len(names) == 1:
            subject = "%s sales tax threshold crossed" % names[0]
        else:
            subject = "Sales tax thresholds crossed: %s" % ", ".join(names)
        company = breaches[0][0].company_id
        blocks = []
        for row, hit in breaches:
            why = []
            if hit["amount_hit"]:
                why.append("the dollar amount")
            if hit["count_hit"]:
                why.append("the transaction count")
            amount = formatLang(self.env, hit["amount"], currency_obj=company.currency_id)
            limit = (
                formatLang(self.env, row.amount_threshold, currency_obj=company.currency_id)
                if row.amount_threshold else "no dollar test"
            )
            count_limit = " of %s" % row.transaction_threshold if row.transaction_threshold else ""
            blocks.append(Markup(
                "<p><strong>{}</strong> crossed {}.</p>"
                "<p>Sales {}, threshold {}. Orders {}{}.<br/>"
                "Measured {}, confirmed orders shipped there. "
                "Wholesale, delivery, and marketplace orders are left out when that state does not count them.</p>"
            ).format(
                escape(row.state_id.name),
                escape(" and ".join(why)),
                escape(amount),
                escape(limit),
                hit["count"],
                escape(count_limit),
                escape(self._format_window(hit["start"], hit["end"])),
            ))
        body = Markup(
            "{}"
            "<p>Register in that state and add a fiscal position for it, with a sequence "
            "between Utah and Out of State, before collecting the tax. "
            "Then take the state off the Out of State position.</p>"
            "<p>This check runs on the 1st of the month and emails again only if a state "
            "drops back under its threshold and later crosses it.</p>"
        ).format(Markup("").join(blocks))
        mail = self.env["mail.mail"].sudo().create({
            "subject": subject,
            "body_html": body,
            "email_to": user.email_formatted or user.email,
            "email_from": company.email_formatted or user.email_formatted or user.email,
            "auto_delete": True,
        })
        if not self.env.context.get("int_nexus_skip_send"):
            mail.send()
