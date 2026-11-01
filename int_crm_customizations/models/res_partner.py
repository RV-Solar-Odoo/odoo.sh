from odoo import api, fields, models

# Utah form TC-721.
TAX_EXEMPTION_REASONS = [
    ("resale", "Resale or Re-lease"),
    ("industrial_fuels", "Fuels, Gas, Electricity (predominantly industrial use)"),
    ("mfg_mining_equipment", "Machinery & Equipment / Parts – Manufacturing Facility, Mining Activity, Web Search Portal or Medical Laboratory"),
    ("electronic_payment_equipment", "Machinery & Equipment / Parts – Electronic Payment Service"),
    ("admissions_user_fees_equipment", "Machinery or Equipment Used by Payers of Admissions or User Fees"),
    ("life_science_rd", "Life Science Research and Development Facility"),
    ("service_provider_consumables", "Service Provider Consumables"),
    ("commercial_airlines", "Commercial Airlines"),
    ("commercials_films_tapes", "Commercials, Films, Audio and Video Tapes"),
    ("mailing_lists", "Mailing Lists"),
    ("semiconductor", "Semiconductor Fabricating, Processing or R&D Material"),
    ("telecom_equipment", "Telecommunications Equipment, Machinery or Software"),
    ("aircraft_mro", "Aircraft Maintenance, Repair and Overhaul Provider"),
    ("ski_resort", "Ski Resort"),
    ("data_center", "Qualifying Data Center"),
    ("refinery", "Refinery Machinery, Equipment and Normal Repair or Replacement Parts"),
    ("pollution_control", "Pollution Control Facility"),
    ("municipal_energy", "Municipal Energy"),
    ("alternative_energy", "Alternative Energy"),
    ("alt_energy_rd", "Research and Development of Alternative Energy Technology"),
    ("electrical_coop", "Electrical Cooperatives"),
    ("locomotive_fuel", "Locomotive Fuel"),
    ("leasebacks", "Leasebacks"),
    ("film_television", "Film and Television"),
    ("out_of_state_construction", "Out-of-State Construction Materials"),
    ("agricultural", "Agricultural Producer"),
    ("tourism_vehicle_rental", "Tourism/Motor Vehicle Rental"),
    ("textbooks_higher_ed", "Textbooks for Higher Education"),
    ("direct_mail", "Direct Mail"),
    ("energy_storage_mfg", "Qualifying Energy Storage Manufacturing Facility"),
    ("sports_zone_construction", "Sports Zone Construction Materials"),
    ("government", "Government, Native American Tribe or Public School (form TC-721G)"),
    ("religious_charitable", "Religious or Charitable Organization (form TC-721RC)"),
]


class ResPartner(models.Model):
    _inherit = "res.partner"

    x_is_tax_exempt = fields.Boolean(string="Tax Exempt?", default=False)
    x_tax_exemption_reason = fields.Selection(
        TAX_EXEMPTION_REASONS,
        string="Tax Exemption Reason",
        compute="_compute_x_tax_exemption_reason",
        store=True,
        readonly=False,
    )
    x_tax_exemption_document = fields.Binary(string="Tax Exemption Certificate", attachment=True)
    x_tax_exemption_document_filename = fields.Char()

    @api.depends("x_is_tax_exempt")
    def _compute_x_tax_exemption_reason(self):
        for partner in self:
            if not partner.x_is_tax_exempt:
                partner.x_tax_exemption_reason = False

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + [
            "x_is_tax_exempt",
            "x_tax_exemption_reason",
            "x_tax_exemption_document",
            "x_tax_exemption_document_filename",
        ]
