from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNexusThreshold(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us = cls.env.ref("base.us")
        cls.company = cls.env.company
        cls.company.country_id = cls.us
        if not cls.env.user.email:
            cls.env.user.email = "nexus-test@example.com"
        cls.env["ir.config_parameter"].sudo().set_param(
            "int_account.nexus_alert_user_id", str(cls.env.user.id),
        )
        cls.ca = cls.env["res.country.state"].search([
            ("country_id", "=", cls.us.id),
            ("code", "=", "CA"),
        ], limit=1)
        cls.ny = cls.env["res.country.state"].search([
            ("country_id", "=", cls.us.id),
            ("code", "=", "NY"),
        ], limit=1)
        cls.partner = cls.env["res.partner"].create({
            "name": "California customer",
            "country_id": cls.us.id,
            "state_id": cls.ca.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Nexus widget",
            "list_price": 100.0,
            "type": "consu",
        })
        Threshold = cls.env["int.nexus.threshold"]
        Threshold.search([("company_id", "=", cls.company.id)]).unlink()
        cls.california = Threshold.create({
            "state_id": cls.ca.id,
            "company_id": cls.company.id,
            "amount_threshold": 500,
            "transaction_threshold": 3,
            "trigger": "or",
            "period": "either_year",
        })
        cls.new_york = Threshold.create({
            "state_id": cls.ny.id,
            "company_id": cls.company.id,
            "amount_threshold": 500,
            "transaction_threshold": 3,
            "trigger": "and",
            "period": "either_year",
        })

    def _order(self, amount, state, when, extra_lines=None):
        self.product.list_price = amount
        lines = [(0, 0, {
            "product_id": self.product.id,
            "product_uom_qty": 1,
            "price_unit": amount,
        })]
        prices = [amount]
        for product, price in extra_lines or []:
            product.list_price = price
            lines.append((0, 0, {
                "product_id": product.id,
                "product_uom_qty": 1,
                "price_unit": price,
            }))
            prices.append(price)
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "partner_shipping_id": self.partner.id,
            "company_id": self.company.id,
            "order_line": lines,
        })
        order.write({
            "state": "sale",
            "date_order": "%s 12:00:00" % when,
            "partner_shipping_id": self.env["res.partner"].create({
                "name": "Ship %s" % state.code,
                "country_id": self.us.id,
                "state_id": state.id,
                "parent_id": self.partner.id,
                "type": "delivery",
            }).id,
        })
        for line, price in zip(order.order_line, prices):
            line.price_unit = price
        return order

    def _sales_tax(self, name, amount):
        return self.env["account.tax"].create({
            "name": name,
            "amount": amount,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": self.company.id,
        })

    def test_either_test_crosses_on_dollars_alone(self):
        self._order(600, self.ca, "2026-06-01")
        breaches = self.env["int.nexus.threshold"]._collect_breaches(date(2026, 11, 1))
        self.assertEqual([row.state_id for row, _hit in breaches], [self.ca])
        self.assertTrue(self.california.alerted)
        self.assertFalse(self.new_york.alerted)

    def test_second_check_does_not_repeat_the_email(self):
        self._order(600, self.ca, "2026-06-01")
        threshold = self.env["int.nexus.threshold"].with_context(
            int_nexus_skip_send=True,
            int_nexus_today=date(2026, 11, 1),
        )
        threshold.cron_check_nexus()
        self.assertTrue(self.california.alerted)
        mails = self.env["mail.mail"].search([("subject", "ilike", "California sales tax")])
        self.assertEqual(len(mails), 1)
        threshold.cron_check_nexus()
        mails = self.env["mail.mail"].search([("subject", "ilike", "California sales tax")])
        self.assertEqual(len(mails), 1)

    def test_both_tests_wait_for_the_count(self):
        ny_partner = self.env["res.partner"].create({
            "name": "New York ship",
            "country_id": self.us.id,
            "state_id": self.ny.id,
            "type": "delivery",
        })
        order = self._order(600, self.ny, "2026-06-01")
        order.partner_shipping_id = ny_partner
        breaches = self.env["int.nexus.threshold"]._collect_breaches(date(2026, 11, 1))
        self.assertFalse(breaches)
        self.assertFalse(self.new_york.alerted)

    def test_domestic_state_is_not_emailed(self):
        position = self.env["account.fiscal.position"].create({
            "name": "California",
            "company_id": self.company.id,
            "country_id": self.us.id,
            "state_ids": [(6, 0, [self.ca.id])],
            "auto_apply": True,
        })
        self.company.domestic_fiscal_position_id = position
        self._order(600, self.ca, "2026-06-01")
        breaches = self.env["int.nexus.threshold"]._collect_breaches(date(2026, 11, 1))
        self.assertFalse(breaches)

    def test_wholesale_goods_are_left_out(self):
        self.product.taxes_id = self._sales_tax("UT Sales Tax 7.08%", 7.08)
        position = self.env["account.fiscal.position"].create({
            "name": "Wholesale dealer",
            "company_id": self.company.id,
            "int_nexus_resale": True,
        })
        self.california.write({
            "count_resale": False,
            "amount_threshold": 500,
            "transaction_threshold": 0,
        })
        order = self._order(600, self.ca, "2026-06-01")
        order.fiscal_position_id = position
        self.env["int.nexus.threshold"]._collect_breaches(date(2026, 11, 1))
        self.assertAlmostEqual(self.california.last_amount, 0.0)
        self.assertEqual(self.california.last_count, 0)
        self.assertFalse(self.california.alerted)

    def test_out_of_state_retail_still_counts(self):
        self.product.taxes_id = self._sales_tax("UT Sales Tax 7.08%", 7.08)
        placeholder = self._sales_tax("Out of State", 0.0)
        placeholder.int_nexus_treatment = "not_collecting"
        self.california.write({
            "count_taxable_goods": True,
            "count_exempt_goods": False,
            "count_resale": False,
            "amount_threshold": 500,
            "transaction_threshold": 0,
        })
        order = self._order(600, self.ca, "2026-06-01")
        order.order_line.tax_ids = placeholder
        self.env["int.nexus.threshold"]._collect_breaches(date(2026, 11, 1))
        self.assertAlmostEqual(self.california.last_amount, 600.0)
        self.assertTrue(self.california.alerted)

    def test_untaxed_delivery_is_left_out(self):
        self.product.taxes_id = self._sales_tax("UT Sales Tax 7.08%", 7.08)
        delivery = self.env["product.product"].create({
            "name": "Delivery",
            "type": "service",
            "list_price": 80.0,
        })
        self.california.write({
            "count_taxable_services": False,
            "count_exempt_services": False,
            "amount_threshold": 650,
            "transaction_threshold": 0,
        })
        self._order(600, self.ca, "2026-06-01", extra_lines=[(delivery, 80.0)])
        self.env["int.nexus.threshold"]._collect_breaches(date(2026, 11, 1))
        self.assertAlmostEqual(self.california.last_amount, 600.0)
        self.assertEqual(self.california.last_count, 1)
        self.assertFalse(self.california.alerted)

    def test_marketplace_order_is_left_out(self):
        self.california.write({
            "count_marketplace": False,
            "amount_threshold": 500,
            "transaction_threshold": 0,
        })
        order = self._order(600, self.ca, "2026-06-01")
        order.int_marketplace_collected = True
        self.env["int.nexus.threshold"]._collect_breaches(date(2026, 11, 1))
        self.assertAlmostEqual(self.california.last_amount, 0.0)
        self.assertEqual(self.california.last_count, 0)

    def test_returned_quantity_is_left_out_only_when_the_state_says_so(self):
        self.california.exclude_returned = True
        self.assertEqual(self.california._kept_ratio(4, 1), 0.75)
        self.assertEqual(self.california._kept_ratio(4, 4), 0.0)
        self.california.exclude_returned = False
        self.assertEqual(self.california._kept_ratio(4, 4), 1.0)

    def test_named_wholesale_position_and_out_of_state_tax_are_tagged(self):
        position = self.env["account.fiscal.position"].create({
            "name": "Wholesale — tax exempt",
            "company_id": self.company.id,
        })
        tax = self._sales_tax("Out of State", 0.0)
        self.env["int.nexus.threshold"].mark_sale_treatments()
        self.assertTrue(position.int_nexus_resale)
        self.assertEqual(tax.int_nexus_treatment, "not_collecting")

    def test_windows_match_the_state_document(self):
        windows = self.env["int.nexus.threshold"]._period_windows
        today = date(2026, 11, 1)
        self.assertEqual(windows("previous_year", today), [(date(2025, 1, 1), date(2025, 12, 31))])
        self.assertEqual(windows("current_year", today), [(date(2026, 1, 1), today)])
        self.assertEqual(windows("trailing_12", today), [(date(2025, 11, 1), today)])
        self.assertEqual(windows("four_quarters", today), [(date(2025, 9, 1), date(2026, 8, 31))])
        self.assertEqual(windows("sept_30", today), [(date(2025, 10, 1), date(2026, 9, 30))])

    def test_seed_does_not_duplicate(self):
        threshold = self.env["int.nexus.threshold"]
        threshold.search([("company_id", "=", self.company.id)]).unlink()
        threshold.seed_defaults()
        first = threshold.search_count([("company_id", "=", self.company.id)])
        self.california = threshold.search([
            ("company_id", "=", self.company.id),
            ("state_id", "=", self.ca.id),
        ])
        self.california.amount_threshold = 1
        threshold.seed_defaults()
        self.assertEqual(threshold.search_count([("company_id", "=", self.company.id)]), first)
        self.assertEqual(self.california.amount_threshold, 1)
