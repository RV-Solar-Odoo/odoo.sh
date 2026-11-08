from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.int_helpdesk_customizations.models.help_feedback import (
    MAX_UPLOAD_BYTES,
    NO_ORDERS_MESSAGE,
)


class Upload:
    def __init__(self, filename, mimetype, content):
        self.filename = filename
        self.mimetype = mimetype
        self.content_type = mimetype
        self._content = content

    def read(self):
        return self._content


@tagged("post_install", "-at_install")
class TestHelpFeedback(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Help Feedback Test Co"})
        cls.env.user.write({"company_ids": [Command.link(cls.company.id)]})
        if not cls.env.user.email:
            cls.env.user.email = "help-staff@example.com"
        cls.public_user = cls.env.ref("base.public_user")
        cls.public_partner = cls.public_user.partner_id.commercial_partner_id
        cls.public_pl = cls.env["product.pricelist"].create({
            "name": "Help Public",
            "company_id": cls.company.id,
            "currency_id": cls.company.currency_id.id,
        })
        cls.dealer_pl = cls.env["product.pricelist"].create({
            "name": "Help Dealer",
            "company_id": cls.company.id,
            "currency_id": cls.company.currency_id.id,
        })
        cls._set_pricelist(cls.public_partner, cls.public_pl)
        cls.dealer = cls.env["res.partner"].create({
            "name": "Approved Dealer",
            "email": "approved-dealer@example.com",
        })
        cls.retail = cls.env["res.partner"].create({
            "name": "Retail Contact",
            "email": "retail-help@example.com",
        })
        cls._set_pricelist(cls.dealer, cls.dealer_pl)
        cls._set_pricelist(cls.retail, cls.public_pl)
        cls.dealer_user = cls._portal_user(cls.dealer, "int.help.dealer", "int-help-dealer@example.com")
        cls.retail_user = cls._portal_user(cls.retail, "int.help.retail", "int-help-retail@example.com")
        cls.product = cls.env["product.product"].create({
            "name": "Victron MultiPlus",
            "default_code": "PMP",
            "list_price": 100.0,
            "type": "consu",
            "sale_ok": True,
        })
        cls.other_product = cls.env["product.product"].create({
            "name": "Not On The Order",
            "default_code": "NOPE",
            "list_price": 50.0,
            "type": "consu",
            "sale_ok": True,
        })
        cls.order = cls._order(cls.dealer, cls.company, cls.product, "sale")
        cls.team = cls.env["helpdesk.team"].with_company(cls.company).create({
            "name": "Test Dealer Support",
            "company_id": cls.company.id,
            "member_ids": [Command.set([cls.env.user.id])],
        })
        Tag = cls.env["helpdesk.tag"]
        cls.tag_return = Tag.create({"name": "Test Return", "color": 1})
        cls.tag_warranty = Tag.create({"name": "Test Warranty", "color": 2})
        cls.tag_feedback = Tag.create({"name": "Test Feedback", "color": 4})
        cls.tag_part = Tag.create({"name": "Test Part", "color": 10})
        cls.tags = cls.tag_return | cls.tag_warranty | cls.tag_feedback | cls.tag_part
        cls.company.write({
            "int_help_team_id": cls.team.id,
            "int_help_tag_return_id": cls.tag_return.id,
            "int_help_tag_warranty_id": cls.tag_warranty.id,
            "int_help_tag_feedback_id": cls.tag_feedback.id,
            "int_help_tag_part_id": cls.tag_part.id,
        })
        Alert = cls.env["int.helpdesk.alert.list"]
        cls.alerts = Alert
        for code, name in (
            ("help_return", "Returns"),
            ("help_warranty", "Warranty claims"),
            ("help_feedback", "Feedback"),
            ("help_part", "Part requests"),
        ):
            cls.alerts |= Alert.create({
                "name": name,
                "code": code,
                "company_id": cls.company.id,
                "user_ids": [Command.set([cls.env.user.id])],
            })

    @classmethod
    def _set_pricelist(cls, partner, pricelist):
        partner.with_company(cls.company).sudo().write({
            "specific_property_product_pricelist": pricelist.id,
        })

    @classmethod
    def _portal_user(cls, partner, login, email):
        return cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name,
            "login": login,
            "email": email,
            "partner_id": partner.id,
            "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
            "company_id": cls.company.id,
            "company_ids": [Command.set([cls.company.id])],
        })

    @classmethod
    def _order(cls, partner, company, product, state, when=None):
        order = cls.env["sale.order"].with_company(company).create({
            "partner_id": partner.id,
            "company_id": company.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            })],
        })
        values = {"state": state}
        if when:
            values["date_order"] = when
        order.write(values)
        return order

    def _submit(self, kind, data, files=None, user=None):
        return self.env["helpdesk.ticket"]._int_help_submit(
            user or self.dealer_user,
            self.company,
            kind,
            data,
            files or [],
        )

    def test_approved_dealer_flag(self):
        self.assertEqual(
            self.dealer.with_company(self.company).property_product_pricelist,
            self.dealer_pl,
        )
        self.assertEqual(
            self.public_partner.with_company(self.company).property_product_pricelist,
            self.public_pl,
        )
        self.assertTrue(self.dealer._int_help_is_approved_dealer(self.company))
        self.assertTrue(self.dealer_user._int_help_is_approved_dealer(self.company))
        self.assertFalse(self.retail._int_help_is_approved_dealer(self.company))
        self.assertFalse(self.retail_user._int_help_is_approved_dealer(self.company))
        self.assertFalse(self.public_partner._int_help_is_approved_dealer(self.company))
        self.assertFalse(self.public_user._int_help_is_approved_dealer(self.company))

    def test_hub_visibility(self):
        self.assertTrue(self.dealer_user.with_company(self.company)._int_help_hub_visible())
        self.assertTrue(self.env.user.with_company(self.company)._int_help_hub_visible())
        self.assertFalse(self.retail_user.with_company(self.company)._int_help_hub_visible())
        self.assertFalse(self.public_user.with_company(self.company)._int_help_hub_visible())
        self.company.int_help_team_id = False
        self.assertFalse(self.dealer_user.with_company(self.company)._int_help_hub_visible())

    def test_each_kind_uses_its_tag_and_team(self):
        cases = {
            "return": {
                "order_id": str(self.order.id),
                "product_id": str(self.product.id),
                "quantity": "2",
                "reason": "wrong_item",
                "serial": "SN-1",
                "details": "Arrived open",
            },
            "warranty": {
                "order_id": str(self.order.id),
                "product_id": str(self.product.id),
                "product_text": "Victron MultiPlus",
                "serial": "SN-9",
                "install_date": "2024-05-01",
                "failure": "No output",
            },
            "feedback": {
                "area": "website",
                "description": "<b>boom</b>",
            },
            "part": {
                "manufacturer": "Victron",
                "part": "ORION-123",
                "qty_per_year": "12",
                "link": "https://example.com/orion",
            },
        }
        tags = {
            "return": self.tag_return,
            "warranty": self.tag_warranty,
            "feedback": self.tag_feedback,
            "part": self.tag_part,
        }
        labels = {
            "return": "[Return]",
            "warranty": "[Warranty Claim]",
            "feedback": "[Feedback]",
            "part": "[Part Request]",
        }
        for kind, data in cases.items():
            files = []
            if kind == "warranty":
                files = [Upload("clip.mp4", "video/mp4", b"video")]
            result = self._submit(kind, data, files)
            self.assertFalse(result.get("error"), result.get("error"))
            ticket = result["ticket"]
            self.assertEqual(ticket.team_id, self.team)
            self.assertIn(tags[kind], ticket.tag_ids)
            self.assertTrue(ticket.name.startswith(labels[kind]))
            self.assertIn("\u2013", ticket.name)
            self.assertEqual(ticket.partner_id, self.dealer)
        feedback = self.env["helpdesk.ticket"].search([
            ("partner_id", "=", self.dealer.id),
            ("tag_ids", "in", self.tag_feedback.id),
        ], limit=1)
        self.assertIn("&lt;b&gt;boom&lt;/b&gt;", str(feedback.description))
        self.assertNotIn("<b>boom</b>", str(feedback.description))
        returned = self.env["helpdesk.ticket"].search([
            ("partner_id", "=", self.dealer.id),
            ("tag_ids", "in", self.tag_return.id),
        ], limit=1)
        self.assertIn(self.order.name, returned.name)
        self.assertIn(self.product.name, returned.name)
        if "sale_order_id" in returned._fields:
            self.assertEqual(returned.sale_order_id, self.order)
        if "product_id" in returned._fields:
            self.assertEqual(returned.product_id, self.product)
        note = self.order.message_ids.filtered(lambda message: "Help" in (message.body or ""))
        self.assertTrue(note)

    def test_other_orders_are_rejected(self):
        other = self.env["res.partner"].create({"name": "Someone Else"})
        other_company = self.env["res.company"].create({"name": "Other Help Co"})
        self.env.user.write({"company_ids": [Command.link(other_company.id)]})
        orders = [
            self._order(other, self.company, self.product, "sale"),
            self._order(self.dealer, self.company, self.product, "draft"),
            self._order(self.dealer, self.company, self.product, "cancel"),
            self._order(self.dealer, other_company, self.product, "sale"),
            self._order(
                self.dealer,
                self.company,
                self.product,
                "sale",
                fields.Datetime.now() - relativedelta(months=25),
            ),
        ]
        for order in orders:
            result = self._submit("return", {
                "order_id": str(order.id),
                "product_id": str(self.product.id),
                "quantity": "1",
                "reason": "other",
            })
            self.assertFalse(result.get("ticket"))
            self.assertIn("cannot be used", result["error"])

    def test_product_not_on_the_order_is_rejected(self):
        result = self._submit("return", {
            "order_id": str(self.order.id),
            "product_id": str(self.other_product.id),
            "quantity": "1",
            "reason": "damaged",
        })
        self.assertFalse(result.get("ticket"))
        self.assertIn("product", result["error"].lower())

    def test_order_lines_stay_on_the_dealers_order(self):
        Ticket = self.env["helpdesk.ticket"]
        lines = Ticket._int_help_order_line_options(self.dealer_user, self.company, self.order.id)
        self.assertEqual([line["product_id"] for line in lines], [self.product.id])
        other = self.env["res.partner"].create({"name": "Hidden Order Partner"})
        hidden = self._order(other, self.company, self.other_product, "sale")
        self.assertEqual(
            Ticket._int_help_order_line_options(self.dealer_user, self.company, hidden.id),
            [],
        )

    def test_attachment_rules(self):
        good = self._submit("return", {
            "order_id": str(self.order.id),
            "product_id": str(self.product.id),
            "quantity": "1",
            "reason": "ordered_error",
        }, [Upload("photo.png", "image/png", b"\x89PNG\r\n")])
        ticket = good["ticket"]
        attachment = self.env["ir.attachment"].search([
            ("res_model", "=", "helpdesk.ticket"),
            ("res_id", "=", ticket.id),
        ])
        self.assertEqual(len(attachment), 1)
        self.assertFalse(attachment.public)
        self.assertEqual(attachment.name, "photo.png")
        self.assertEqual(attachment.mimetype, "image/png")

        blocked = self._submit("feedback", {
            "area": "shipping",
            "description": "Late",
        }, [Upload("notes.exe", "application/octet-stream", b"MZ")])
        self.assertFalse(blocked.get("ticket"))
        self.assertIn("not allowed", blocked["error"])

        oversized = self._submit("feedback", {
            "area": "billing",
            "description": "Invoice",
        }, [Upload("photo.jpg", "image/jpeg", b"x" * (MAX_UPLOAD_BYTES + 1))])
        self.assertFalse(oversized.get("ticket"))
        self.assertIn("20 MB", oversized["error"])

    def test_eleventh_ticket_in_an_hour_is_rejected(self):
        Ticket = self.env["helpdesk.ticket"].with_company(self.company).with_context(
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            mail_notrack=True,
            tracking_disable=True,
            mail_activity_automation_skip=True,
        )
        Ticket.create([{
            "name": f"Existing {index}",
            "team_id": self.team.id,
            "partner_id": self.dealer.id,
            "company_id": self.company.id,
            "description": "existing",
            "tag_ids": [Command.set([self.tag_feedback.id])],
        } for index in range(10)])
        domain = [
            ("partner_id", "=", self.dealer.id),
            ("tag_ids", "in", self.tags.ids),
            ("create_date", ">=", fields.Datetime.now() - timedelta(hours=1)),
        ]
        self.assertEqual(self.env["helpdesk.ticket"].search_count(domain), 10)
        result = self._submit("feedback", {
            "area": "other",
            "description": "One more",
        })
        self.assertFalse(result.get("ticket"))
        self.assertIn("10", result["error"])
        self.assertEqual(self.env["helpdesk.ticket"].search_count(domain), 10)

    def test_return_with_no_orders_explains_that(self):
        partner = self.env["res.partner"].create({
            "name": "Dealer With No Orders",
            "email": "no-orders@example.com",
        })
        self._set_pricelist(partner, self.dealer_pl)
        user = self._portal_user(partner, "int.help.no.orders", "no-orders-user@example.com")
        prepared = self.env["helpdesk.ticket"]._int_help_prepare(user, self.company, "return")
        self.assertFalse(prepared["orders"])
        self.assertEqual(prepared["notice"], NO_ORDERS_MESSAGE)
        self.assertIn("No orders found", prepared["notice"])
        self.assertIn("Feedback", prepared["notice"])
        result = self._submit("return", {
            "order_id": str(self.order.id),
            "product_id": str(self.product.id),
            "quantity": "1",
            "reason": "other",
        }, user=user)
        self.assertFalse(result.get("ticket"))
        self.assertEqual(result["error"], NO_ORDERS_MESSAGE)

    def test_setup_creates_team_tags_and_alerts_once(self):
        company = self.env["res.company"].create({"name": "Seed Help Co"})
        self.env.user.write({"company_ids": [Command.link(company.id)]})
        company._int_help_setup()
        self.assertEqual(company.int_help_team_id.name, "Dealer Support")
        self.assertEqual(company.int_help_team_id.company_id, company)
        self.assertTrue(company.int_help_team_id.member_ids)
        self.assertEqual(company.int_help_tag_return_id, self.env.ref("int_helpdesk_customizations.tag_help_return"))
        self.assertTrue(company.int_help_tag_warranty_id)
        self.assertTrue(company.int_help_tag_feedback_id)
        self.assertTrue(company.int_help_tag_part_id)
        alerts = self.env["int.helpdesk.alert.list"].search([("company_id", "=", company.id)])
        self.assertEqual(set(alerts.mapped("code")), {"help_return", "help_warranty", "help_feedback", "help_part"})
        alerts.write({"user_ids": [Command.set([self.env.user.id])]})
        team = company.int_help_team_id
        company._int_help_setup()
        self.assertEqual(company.int_help_team_id, team)
        self.assertEqual(alerts.user_ids, self.env.user)

    def test_notify_assigns_the_only_recipient(self):
        ticket = self.env["helpdesk.ticket"].with_company(self.company).with_context(
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            tracking_disable=True,
        ).create({
            "name": "[Return] S0001 \u2013 Victron MultiPlus",
            "team_id": self.team.id,
            "partner_id": self.dealer.id,
            "company_id": self.company.id,
            "description": "<ul><li>Order</li></ul>",
            "tag_ids": [Command.set([self.tag_return.id])],
        })
        if "user_id" in ticket._fields:
            ticket.user_id = False
        self.env["int.helpdesk.alert.list"]._int_notify(
            "help_return", ticket, ticket.name, self.company,
        )
        if "user_id" in ticket._fields:
            self.assertEqual(ticket.user_id, self.env.user)
        self.assertIn(self.env.user.partner_id, ticket.message_partner_ids)
        activity = self.env["mail.activity"].search([
            ("res_model", "=", "helpdesk.ticket"),
            ("res_id", "=", ticket.id),
            ("user_id", "=", self.env.user.id),
        ])
        self.assertTrue(activity)
        mail = self.env["mail.mail"].search([
            ("model", "=", "helpdesk.ticket"),
            ("res_id", "=", ticket.id),
        ], limit=1)
        self.assertTrue(mail)
        self.assertIn(self.env.user.email, mail.email_to or "")
