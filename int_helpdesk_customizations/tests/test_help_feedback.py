from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.website.tools import MockRequest

from odoo.addons.int_helpdesk_customizations.models.help_feedback import (
    MAX_UPLOAD_BYTES,
    TYPED_ORDER,
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
        cls.returns_team = cls.env["helpdesk.team"].with_company(cls.company).create({
            "name": "RVSB Returns",
            "company_id": cls.company.id,
            "member_ids": [Command.set([cls.env.user.id])],
        })
        cls.general_team = cls.env["helpdesk.team"].with_company(cls.company).create({
            "name": "General Inquiries",
            "company_id": cls.company.id,
            "member_ids": [Command.set([cls.env.user.id])],
        })
        cls.team = cls.general_team
        Tag = cls.env["helpdesk.tag"]
        cls.tag_return = Tag.create({"name": "Test Return", "color": 1})
        cls.tag_warranty = Tag.create({"name": "Test Warranty", "color": 2})
        cls.tag_feedback = Tag.create({"name": "Test Feedback", "color": 4})
        cls.tag_part = Tag.create({"name": "Test Part", "color": 10})
        cls.tags = cls.tag_return | cls.tag_warranty | cls.tag_feedback | cls.tag_part
        cls.dealer_category = cls.env["res.partner.category"].create({"name": "RVSB Dealer"})
        cls.dealer.write({"category_id": [Command.link(cls.dealer_category.id)]})
        cls.company.write({
            "int_help_team_return_id": cls.returns_team.id,
            "int_help_team_warranty_id": cls.returns_team.id,
            "int_help_team_feedback_id": cls.general_team.id,
            "int_help_team_part_id": cls.general_team.id,
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
        if kind == "return":
            # Required on every return, as on the public returns form.
            data = {"packaging": "yes", "condition": "unopened", **data}
        return self.env["helpdesk.ticket"]._int_help_submit(
            user or self.dealer_user,
            self.company,
            kind,
            data,
            files or [],
        )

    def test_second_submit_returns_the_same_ticket(self):
        data = {
            "product_text": "555",
            "serial": "6666",
            "install_date": "2026-11-03",
            "failure": "pls help",
        }
        first = self._submit("warranty", data)
        self.assertFalse(first.get("error"), first.get("error"))
        second = self._submit("warranty", data)
        self.assertEqual(second["ticket"], first["ticket"])
        self.assertEqual(
            self.env["helpdesk.ticket"].search_count([("name", "=", first["ticket"].name)]),
            1,
        )
        other = dict(data, failure="A different failure")
        third = self._submit("warranty", other)
        self.assertFalse(third.get("error"), third.get("error"))
        self.assertNotEqual(third["ticket"], first["ticket"])

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
        # Retail users get Help & Feedback too.
        self.assertTrue(self.retail_user.with_company(self.company)._int_help_hub_visible())
        self.assertFalse(self.public_user.with_company(self.company)._int_help_hub_visible())
        self.company.int_help_team_return_id = False
        self.assertFalse(self.dealer_user.with_company(self.company)._int_help_hub_visible())

    def test_each_kind_uses_its_tag_and_team(self):
        cases = {
            "return": {
                "order_id": str(self.order.id),
                "product_id": str(self.product.id),
                "quantity": "2",
                "reason": "wrong_product",
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
            expected_team = self.returns_team if kind in ("return", "warranty") else self.general_team
            self.assertEqual(ticket.team_id, expected_team)
            self.assertIn(tags[kind], ticket.tag_ids)
            self.assertIn("RVSB Dealer", ticket.tag_ids.mapped("name"))
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
            "reason": "defective",
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

    def test_return_lists_only_physical_items(self):
        Ticket = self.env["helpdesk.ticket"]
        order = self._order(self.dealer, self.company, self.product, "draft")
        shipping = self.env["product.product"].create({"name": "Pickup in store", "type": "service"})
        discount = self.env["product.product"].create({"name": "100% off your order", "type": "service"})
        delivery_line = {"product_id": shipping.id, "product_uom_qty": 1, "price_unit": 0.0}
        if "is_delivery" in self.env["sale.order.line"]._fields:
            # A delivery line can be a goods-type product too; is_delivery still drops it.
            goods_shipping = self.env["product.product"].create({"name": "Freight", "type": "consu"})
            delivery_line = {"product_id": goods_shipping.id, "product_uom_qty": 1, "price_unit": 0.0, "is_delivery": True}
        order.write({"order_line": [
            Command.create(delivery_line),
            Command.create({"product_id": discount.id, "product_uom_qty": 1, "price_unit": -100.0}),
            Command.create({"display_type": "line_note", "name": "Leave at the door"}),
        ]})
        order.action_confirm()
        options = Ticket._int_help_order_line_options(self.dealer_user, self.company, order.id)
        self.assertEqual([line["product_id"] for line in options], [self.product.id])
        self.assertFalse(Ticket._int_help_order_product(order, discount.id))
        self.assertEqual(Ticket._int_help_order_product(order, self.product.id), self.product)

    def test_attachment_rules(self):
        good = self._submit("return", {
            "order_id": str(self.order.id),
            "product_id": str(self.product.id),
            "quantity": "1",
            "reason": "not_needed",
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

    def test_return_with_no_orders_takes_a_typed_order(self):
        partner = self.env["res.partner"].create({
            "name": "Dealer With No Orders",
            "email": "no-orders@example.com",
        })
        self._set_pricelist(partner, self.dealer_pl)
        user = self._portal_user(partner, "int.help.no.orders", "no-orders-user@example.com")
        prepared = self.env["helpdesk.ticket"]._int_help_prepare(user, self.company, "return")
        self.assertFalse(prepared["orders"])
        self.assertFalse(prepared["notice"])
        result = self._submit("return", {
            "order_id": TYPED_ORDER,
            "order_ref": "GUEST-1042",
            "product_text": "SmartSolar 100/30",
            "quantity": "1",
            "reason": "not_needed",
        }, user=user)
        self.assertFalse(result.get("error"), result.get("error"))
        ticket = result["ticket"]
        self.assertEqual(ticket.team_id, self.returns_team)
        self.assertIn(self.tag_return, ticket.tag_ids)
        self.assertIn("GUEST-1042", ticket.name)
        self.assertIn("SmartSolar 100/30", ticket.name)
        self.assertIn("GUEST-1042", str(ticket.description))
        if "sale_order_id" in ticket._fields:
            self.assertFalse(ticket.sale_order_id)

    def test_typed_return_needs_the_order_number_and_product(self):
        result = self._submit("return", {
            "order_id": TYPED_ORDER,
            "quantity": "1",
            "reason": "other",
        })
        self.assertFalse(result.get("ticket"))
        self.assertIn("Order number", result["error"])
        self.assertIn("Product", result["error"])

    def test_open_returns_list(self):
        Ticket = self.env["helpdesk.ticket"]
        returned = self._submit("return", {
            "order_id": str(self.order.id),
            "product_id": str(self.product.id),
            "quantity": "1",
            "reason": "defective",
        })["ticket"]
        warranty = self._submit("warranty", {
            "product_text": "Victron MultiPlus",
            "serial": "SN-2",
            "install_date": "2024-05-01",
            "failure": "No output",
        })["ticket"]
        colleague = self.env["res.partner"].create({
            "name": "Dealer Colleague",
            "parent_id": self.dealer.id,
            "email": "colleague@example.com",
        })
        # The public Returns form makes tickets like this one, without the Help & Feedback tag.
        public_form = Ticket.create({
            "name": "Return from the website form",
            "team_id": self.returns_team.id,
            "partner_id": colleague.id,
        })
        stranger = Ticket.create({
            "name": "Someone else's return",
            "team_id": self.returns_team.id,
            "partner_id": self.retail.id,
        })
        closed = Ticket.create({
            "name": "Finished return",
            "team_id": self.returns_team.id,
            "partner_id": self.dealer.id,
        })
        done = self.env["helpdesk.stage"].create({
            "name": "Done",
            "fold": True,
            "team_ids": [Command.link(self.returns_team.id)],
        })
        closed.stage_id = done
        listed = Ticket._int_help_open_returns(self.dealer_user, self.company)
        self.assertIn(returned, listed)
        self.assertIn(public_form, listed)
        self.assertNotIn(warranty, listed)
        self.assertNotIn(stranger, listed)
        self.assertNotIn(closed, listed)

    def test_setup_uses_existing_teams_and_does_not_create_one(self):
        company = self.env["res.company"].create({"name": "Seed Help Co"})
        self.env.user.write({"company_ids": [Command.link(company.id)]})
        company._int_help_setup()
        self.assertFalse(company.int_help_team_return_id)
        self.assertFalse(company.int_help_team_warranty_id)
        self.assertFalse(company.int_help_team_feedback_id)
        self.assertFalse(company.int_help_team_part_id)
        self.assertFalse(self.env["helpdesk.team"].search([
            ("company_id", "=", company.id),
            ("name", "=", "Dealer Support"),
        ]))
        returns = self.env["helpdesk.team"].with_company(company).create({
            "name": "RVSB Returns",
            "company_id": company.id,
            "member_ids": [Command.set([self.env.user.id])],
        })
        general = self.env["helpdesk.team"].with_company(company).create({
            "name": "General Inquiries",
            "company_id": company.id,
            "member_ids": [Command.set([self.env.user.id])],
        })
        decoy = self.env["helpdesk.team"].with_company(company).create({
            "name": "Dealer Support",
            "company_id": company.id,
            "member_ids": [Command.set([self.env.user.id])],
        })
        company._int_help_setup()
        self.assertEqual(company.int_help_team_return_id, returns)
        self.assertEqual(company.int_help_team_warranty_id, returns)
        self.assertEqual(company.int_help_team_feedback_id, general)
        self.assertEqual(company.int_help_team_part_id, general)
        self.assertFalse(decoy.active)
        self.assertEqual(
            company.int_help_tag_return_id,
            self.env.ref("int_helpdesk_customizations.tag_help_return"),
        )
        self.assertTrue(company.int_help_tag_warranty_id)
        self.assertTrue(company.int_help_tag_feedback_id)
        self.assertTrue(company.int_help_tag_part_id)
        alerts = self.env["int.helpdesk.alert.list"].search([("company_id", "=", company.id)])
        self.assertEqual(
            set(alerts.mapped("code")),
            {"help_return", "help_warranty", "help_feedback", "help_part"},
        )
        alerts.write({"user_ids": [Command.set([self.env.user.id])]})
        company.int_help_team_warranty_id = general
        company._int_help_setup()
        self.assertEqual(company.int_help_team_warranty_id, general)
        self.assertEqual(company.int_help_team_return_id, returns)
        self.assertEqual(alerts.user_ids, self.env.user)

    def test_ticket_tags_copy_the_contact_tags(self):
        Ticket = self.env["helpdesk.ticket"].with_company(self.company).with_context(
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            tracking_disable=True,
        )
        priced_only = self.env["res.partner"].create({
            "name": "Pricelist Only",
            "email": "pricelist-only@example.com",
        })
        self._set_pricelist(priced_only, self.dealer_pl)
        priced_ticket = Ticket.create({
            "name": "Pricelist does not tag the ticket",
            "team_id": self.general_team.id,
            "partner_id": priced_only.id,
            "company_id": self.company.id,
        })
        self.assertNotIn("RVSB Dealer", priced_ticket.tag_ids.mapped("name"))
        dealer_ticket = Ticket.create({
            "name": "Dealer contact",
            "team_id": self.general_team.id,
            "partner_id": self.dealer.id,
            "company_id": self.company.id,
            "tag_ids": [Command.set([self.tag_feedback.id])],
        })
        self.assertIn(self.tag_feedback, dealer_ticket.tag_ids)
        self.assertIn("RVSB Dealer", dealer_ticket.tag_ids.mapped("name"))
        retail_ticket = Ticket.create({
            "name": "Website question",
            "team_id": self.general_team.id,
            "partner_id": self.retail.id,
            "company_id": self.company.id,
        })
        self.assertNotIn("RVSB Dealer", retail_ticket.tag_ids.mapped("name"))
        bare = Ticket.create({
            "name": "No customer",
            "team_id": self.general_team.id,
            "company_id": self.company.id,
        })
        self.assertNotIn("RVSB Dealer", bare.tag_ids.mapped("name"))

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

    def test_ticket_uses_the_logged_in_dealer_and_queues_a_receipt(self):
        stages = self.env["helpdesk.stage"].search([
            ("team_ids", "in", self.general_team.id),
        ])
        stages.write({"template_id": False})
        result = self._submit("feedback", {
            "area": "shipping",
            "description": "The carton arrived late",
        })
        self.assertFalse(result.get("error"), result.get("error"))
        ticket = result["ticket"]
        email = (self.dealer_user.email or self.dealer.email or "").strip()
        self.assertEqual(ticket.partner_id, self.dealer)
        self.assertEqual(ticket.partner_name, self.dealer.name)
        self.assertEqual(ticket.partner_email, email)
        mail = self.env["mail.mail"].sudo().search([
            ("model", "=", "helpdesk.ticket"),
            ("res_id", "=", ticket.id),
            ("email_to", "ilike", email),
        ])
        self.assertTrue(mail)

    def test_reply_uses_the_customer_email_when_it_differs(self):
        ticket = self.env["helpdesk.ticket"].with_company(self.company).create({
            "name": "Website form",
            "team_id": self.general_team.id,
            "partner_id": self.dealer.id,
            "partner_email": "other@example.com",
            "company_id": self.company.id,
        })
        recipients = ticket._message_get_default_recipients()[ticket.id]
        self.assertEqual(recipients.get("email_to"), "other@example.com")
        self.assertFalse(recipients.get("partner_ids"))

    def _render_rep_card(self, user):
        env = self.env(user=user)
        with MockRequest(env, website=self.env["website"].search([], limit=1)):
            return str(env["ir.qweb"]._render("int_contacts_customizations.portal_sales_rep_card", {}))

    def test_hub_shows_the_sales_rep_card(self):
        arch = self.env.ref("int_helpdesk_customizations.portal_help_hub").get_combined_arch()
        self.assertIn("int_contacts_customizations.portal_sales_rep_card", arch)

        self.assertNotIn("Your Sales Rep", self._render_rep_card(self.dealer_user))

        rep = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Help Hub Rep",
            "login": "help-hub-rep@example.com",
            "email": "help-hub-rep@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.env.ref("base.group_user").id])],
        })
        rep.partner_id.phone = "555-0142"
        self.dealer.user_id = rep
        rendered = self._render_rep_card(self.dealer_user)
        self.assertIn("Your Sales Rep", rendered)
        self.assertIn("Help Hub Rep", rendered)
        self.assertIn('href="mailto:help-hub-rep@example.com"', rendered)
        self.assertIn('href="tel:5550142"', rendered)

    def test_retail_flag_hides_one_form_from_retail_only(self):
        from odoo.addons.int_helpdesk_customizations.models.help_feedback import HELP_KINDS

        retail = self.retail_user.with_company(self.company)
        dealer = self.dealer_user.with_company(self.company)
        self.assertTrue(retail._int_help_kind_allowed("part", self.company))
        HELP_KINDS["part"]["retail"] = False
        try:
            self.assertFalse(retail._int_help_kind_allowed("part", self.company))
            self.assertTrue(dealer._int_help_kind_allowed("part", self.company))
            result = self._submit("part", {"part": "ORION-123"}, user=self.retail_user)
            self.assertTrue(result.get("error"))
        finally:
            HELP_KINDS["part"]["retail"] = True

    def test_retail_return_asks_where_it_was_bought(self):
        Ticket = self.env["helpdesk.ticket"]
        self.assertFalse(Ticket._int_help_prepare(self.dealer_user, self.company, "return")["ask_purchase"])
        prepared = Ticket._int_help_prepare(self.retail_user, self.company, "return")
        self.assertTrue(prepared["ask_purchase"])
        self.assertIn(self.dealer, prepared["dealers"])
        self.assertNotIn(self.retail, prepared["dealers"])
        base = {
            "order_id": TYPED_ORDER,
            "order_ref": "S00999",
            "product_text": "PMP",
            "quantity": "1",
            "reason": "not_needed",
        }
        missing = self._submit("return", base, user=self.retail_user)
        self.assertIn("where you bought it", missing["error"])
        no_dealer = self._submit("return", {**base, "purchase_source": "dealer"}, user=self.retail_user)
        self.assertIn("Choose the dealer", no_dealer["error"])
        not_a_dealer = self._submit("return", {
            **base, "purchase_source": "dealer", "purchase_dealer_id": str(self.retail.id),
        }, user=self.retail_user)
        self.assertIn("Choose the dealer", not_a_dealer["error"])
        result = self._submit("return", {
            **base, "purchase_source": "dealer", "purchase_dealer_id": str(self.dealer.id),
        }, user=self.retail_user)
        self.assertFalse(result.get("error"), result.get("error"))
        ticket = result["ticket"]
        self.assertEqual(ticket.int_help_purchase_source, "dealer")
        self.assertEqual(ticket.int_help_purchase_dealer_id, self.dealer)
        self.assertIn("From one of our dealers: Approved Dealer", str(ticket.description))
        self.assertIn("In original packaging", str(ticket.description))

    def test_return_needs_packaging_and_condition(self):
        result = self.env["helpdesk.ticket"]._int_help_submit(self.dealer_user, self.company, "return", {
            "order_id": str(self.order.id),
            "product_id": str(self.product.id),
            "quantity": "1",
            "reason": "not_needed",
        }, [])
        self.assertIn("original packaging", result["error"])
        self.assertIn("product condition", result["error"])

    def test_part_request_manufacturer_is_optional_and_comments_are_kept(self):
        result = self._submit("part", {"part": "ORION-123\n12V to 12V", "comments": "For a van build"})
        self.assertFalse(result.get("error"), result.get("error"))
        self.assertIn("For a van build", str(result["ticket"].description))
        self.assertTrue(self._submit("part", {"manufacturer": "Victron"}).get("error"))

    def test_order_serials_come_from_delivered_moves(self):
        Ticket = self.env["helpdesk.ticket"]
        options = Ticket._int_help_order_line_options(self.dealer_user, self.company, self.order.id)
        self.assertEqual(options[0]["serials"], [])
        self.assertEqual(Ticket._int_help_order_serials(self.env["sale.order"]), {})
