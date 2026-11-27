from odoo import api, fields, models

# The business address is the lead's own address. Odoo copies it to the contact on conversion.
ADDRESS_FIELDS = ("street", "street2", "city", "zip", "state_id", "country_id")
# The parts that count as "has an address"; a country alone (from geoip or signup) doesn't.
ADDRESS_PARTS = ("street", "street2", "city", "zip", "state_id")
BILLING_FIELDS = (
    "int_billing_street",
    "int_billing_street2",
    "int_billing_city",
    "int_billing_state_text",
    "int_billing_state_id",
    "int_billing_zip",
    "int_billing_country_id",
)
SOCIAL_FIELDS = ("int_facebook", "int_instagram", "int_tiktok", "int_linkedin")
# Fields the website editor may put on the dealer application (data/website_form_fields.xml).
APPLICATION_FORM_FIELDS = [
    "street",
    "street2",
    "city",
    "zip",
    "country_id",
    "website",
    "int_state_text",
    "int_billing_different",
    "int_billing_street",
    "int_billing_street2",
    "int_billing_city",
    "int_billing_state_text",
    "int_billing_zip",
    "int_billing_country_id",
    *SOCIAL_FIELDS,
]


class CrmLead(models.Model):
    _inherit = "crm.lead"

    int_state_text = fields.Char(
        string="State / Province",
        help="The state as typed on the website form. It is matched to State; "
             "it stays here only when it didn't match one.",
    )
    int_billing_different = fields.Boolean(string="Billing Address Is Different")
    int_billing_street = fields.Char(string="Billing Street")
    int_billing_street2 = fields.Char(string="Billing Street 2")
    int_billing_city = fields.Char(string="Billing City")
    int_billing_state_id = fields.Many2one(
        "res.country.state",
        string="Billing State",
        domain="[('country_id', '=?', int_billing_country_id)]",
    )
    int_billing_state_text = fields.Char(
        string="Billing State / Province",
        help="The billing state as typed on the website form, kept only when it didn't match one.",
    )
    int_billing_zip = fields.Char(string="Billing ZIP")
    int_billing_country_id = fields.Many2one("res.country", string="Billing Country")
    int_facebook = fields.Char(string="Facebook")
    int_instagram = fields.Char(string="Instagram")
    int_tiktok = fields.Char(string="TikTok")
    int_linkedin = fields.Char(string="LinkedIn")

    # Website form

    def website_form_input_filter(self, request, values):
        values = super().website_form_input_filter(request, values)
        return self._int_application_values(values)

    @api.model
    def _int_application_values(self, values):
        """Tidy the dealer application before the lead is created: drop billing fields left
        filled after unticking the box, default the country to the US, and match typed states."""
        if not values.get("int_billing_different"):
            for name in BILLING_FIELDS + ("int_billing_different",):
                values.pop(name, None)
        for name in SOCIAL_FIELDS + ("int_state_text", "int_billing_state_text"):
            if name in values:
                values[name] = (values[name] or "").strip() or False
        us = self.env.ref("base.us", raise_if_not_found=False)
        if us and not values.get("country_id") and any(
            values.get(name) for name in ("street", "street2", "city", "zip", "int_state_text")
        ):
            values["country_id"] = us.id
        if values.get("int_billing_different") and not values.get("int_billing_country_id"):
            values["int_billing_country_id"] = values.get("country_id") or (us.id if us else False)
        for text, state_field, country_field in (
            ("int_state_text", "state_id", "country_id"),
            ("int_billing_state_text", "int_billing_state_id", "int_billing_country_id"),
        ):
            state = self._int_match_state(values.get(text), values.get(country_field))
            if state:
                values[state_field] = state.id
                values.pop(text)
        return values

    @api.model
    def _int_match_state(self, typed, country_id):
        """The state whose code or name is ``typed`` ("TX", "Texas"), in the country or the US."""
        typed = (typed or "").strip().rstrip(".").lower()
        if not typed:
            return self.env["res.country.state"]
        country = self.env["res.country"].sudo().browse(country_id).exists() if country_id else None
        country = country or self.env.ref("base.us", raise_if_not_found=False)
        if not country:
            return self.env["res.country.state"]
        states = self.env["res.country.state"].sudo().search([("country_id", "=", country.id)])
        return states.filtered(lambda state: typed in (state.code.lower(), state.name.lower()))[:1]

    # Contact

    def _int_fill_dealer_contact(self, partner):
        """Put the application's addresses on the dealer's company contact without overwriting.

        The business address is written only when the contact has none (all fields or none,
        like Odoo's own sync). A billing address that differs becomes an Invoice address.
        """
        self.ensure_one()
        commercial = partner.commercial_partner_id.sudo()
        if not commercial:
            return
        if any(self[name] for name in ADDRESS_PARTS) and not any(commercial[name] for name in ADDRESS_PARTS):
            values = {name: self[name].id if self._fields[name].type == "many2one" else self[name] for name in ADDRESS_FIELDS}
            if not values["country_id"]:
                values.pop("country_id")
            commercial.write(values)
        self._int_add_billing_address(commercial)

    def _int_add_billing_address(self, commercial):
        """An Invoice address under ``commercial`` from the application's billing address."""
        self.ensure_one()
        if not self.int_billing_different or not (self.int_billing_street or self.int_billing_city):
            return self.env["res.partner"]
        street = (self.int_billing_street or "").strip().lower()
        zip_code = (self.int_billing_zip or "").strip()
        existing = commercial.child_ids.filtered(
            lambda child: child.type == "invoice"
            and (child.street or "").strip().lower() == street
            and (child.zip or "").strip() == zip_code
        )
        if existing:
            return existing[:1]
        billing = self.env["res.partner"].sudo().create({
            "parent_id": commercial.id,
            "type": "invoice",
            "street": self.int_billing_street,
            "street2": self.int_billing_street2,
            "city": self.int_billing_city,
            "state_id": self.int_billing_state_id.id,
            "zip": self.int_billing_zip,
            "country_id": (self.int_billing_country_id or self.country_id).id,
            "company_id": commercial.company_id.id,
        })
        self._int_document_log(self.env._(
            "Added the billing address from the application to %(name)s as an Invoice address.",
            name=commercial.display_name,
        ))
        return billing

    def _int_address_snapshot(self):
        return {lead.id: {name: lead[name] for name in ADDRESS_FIELDS} for lead in self}

    def _int_restore_address(self, snapshot):
        """Linking a contact replaces the lead's address with the contact's (Odoo syncs all or
        none). Keep what the dealer typed on the lead instead."""
        for lead in self:
            before = snapshot.get(lead.id)
            if not before or not any(before[name] for name in ADDRESS_PARTS):
                continue
            if any(lead[name] != before[name] for name in ADDRESS_FIELDS):
                lead.write({name: value.id if isinstance(value, models.BaseModel) else value for name, value in before.items()})

    def _int_link_account_partner(self, partner):
        """Fill the dealer's contact from the application, then link it, keeping the lead's address."""
        self.ensure_one()
        self._int_fill_dealer_contact(partner)
        if self.partner_id == partner:
            return False
        snapshot = self._int_address_snapshot()
        self.partner_id = partner
        self._int_restore_address(snapshot)
        return True

    def _create_customer(self, with_parent=None):
        # Odoo copies the business address; add the billing address under the new company.
        partner = super()._create_customer(with_parent=with_parent)
        self._int_add_billing_address(partner.commercial_partner_id)
        return partner

    def _handle_partner_assignment(self, force_partner_id=False, create_missing=True, with_parent=None):
        # Converting onto an existing customer: fill it from the application without overwriting.
        if not force_partner_id:
            return super()._handle_partner_assignment(force_partner_id, create_missing, with_parent)
        partner = self.env["res.partner"].browse(force_partner_id)
        snapshot = self._int_address_snapshot()
        for lead in self:
            lead._int_fill_dealer_contact(partner)
        res = super()._handle_partner_assignment(force_partner_id, create_missing, with_parent)
        self._int_restore_address(snapshot)
        return res
