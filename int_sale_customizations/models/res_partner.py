import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Swatches on Quote Settings. The accent prints on the quote PDF; everything else is black and white.
QUOTE_ACCENTS = [
    ("#1f2433", "Charcoal"),
    ("#0054a8", "Blue"),
    ("#1f7a4d", "Green"),
    ("#c2410c", "Orange"),
    ("#b3261e", "Red"),
    ("#6d28d9", "Purple"),
]
DEFAULT_ACCENT = "#1f2433"
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_SUBHEADING = 80
MAX_FOOTER = 200
# Fields only the account owner changes, through _int_set_quote_settings.
QUOTE_SETTING_FIELDS = ("int_quote_price_basis", "int_quote_accent", "int_quote_subheading", "int_quote_footer")


def int_clean_accent(value):
    """``#rrggbb`` in lower case, or None when it isn't a colour."""
    value = (value or "").strip()
    if value and not value.startswith("#"):
        value = "#" + value
    return value.lower() if HEX_COLOR.match(value) else None


def _int_luminance(hex_color):
    def channel(part):
        c = int(part, 16) / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(hex_color[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def int_readable_accent(hex_color):
    """The accent darkened until text in it reads on white (4.5:1), so a very light pick still prints legibly."""
    color = int_clean_accent(hex_color) or DEFAULT_ACCENT
    for _step in range(20):
        if (1.05) / (_int_luminance(color) + 0.05) >= 4.5:
            return color
        color = "#" + "".join("%02x" % int(int(color[i:i + 2], 16) * 0.85) for i in (1, 3, 5))
    return color


class ResPartner(models.Model):
    _inherit = "res.partner"

    int_quote_price_basis = fields.Selection(
        [("map", "MAP"), ("msrp", "MSRP")],
        string="Customer quote price",
        default="map",
        help="The starting price on this dealer's customer quotes. MAP or MSRP, never the wholesale price.",
    )
    int_quote_accent = fields.Char(
        string="Quote accent colour",
        help="#rrggbb. Prints on the dealer's customer quote PDF: the top band, headings and total.",
    )
    int_quote_subheading = fields.Char(
        string="Quote subheading",
        help="The line under the company name on the dealer's customer quote PDF.",
    )
    int_quote_footer = fields.Char(
        string="Quote footer line",
        help="One line at the bottom of the dealer's customer quote PDF: terms, licence number or a thank-you.",
    )

    def write(self, vals):
        if any(name in vals for name in QUOTE_SETTING_FIELDS) and not self.env.su and not self.env.user.has_group("base.group_user"):
            raise AccessError(_("Only the account owner can change customer quote settings."))
        if vals.get("int_quote_price_basis") not in (None, "map", "msrp"):
            raise UserError(_("Choose MAP or MSRP."))
        if vals.get("int_quote_accent") and not int_clean_accent(vals["int_quote_accent"]):
            raise UserError(_("Choose an accent colour like #1F7A4D."))
        return super().write(vals)

    def _int_quote_accent(self):
        """The accent as chosen, for the band and rules."""
        self.ensure_one()
        return int_clean_accent(self.commercial_partner_id.int_quote_accent) or DEFAULT_ACCENT

    def _int_quote_accent_text(self):
        """The accent for text, darkened when it is too light to read on white."""
        self.ensure_one()
        return int_readable_accent(self._int_quote_accent())

    @api.model
    def _int_check_quote_owner(self, user):
        if not user or not user.share or not user.int_portal_can("manage_users"):
            raise UserError(_("Only the account owner can change customer quote settings."))

    @api.model
    def _int_set_quote_basis(self, user, basis):
        """Portal owners set the company default. Staff use the contact form."""
        return self._int_set_quote_settings(user, {"price_basis": basis})

    @api.model
    def _int_set_quote_settings(self, user, post, logo=None):
        """Save Quote Settings for the owner's company: default price, accent, subheading,
        footer, and an optional logo upload ``(filename, content)``."""
        self._int_check_quote_owner(user)
        values = {}
        if "price_basis" in post:
            if post.get("price_basis") not in ("map", "msrp"):
                raise UserError(_("Choose MAP or MSRP."))
            values["int_quote_price_basis"] = post["price_basis"]
        if "quote_accent" in post:
            choice = post.get("quote_accent")
            raw = post.get("quote_accent_custom") if choice == "custom" else choice
            accent = int_clean_accent(raw)
            if not accent:
                raise UserError(_("Choose an accent colour like #1F7A4D."))
            values["int_quote_accent"] = accent
        if "quote_subheading" in post:
            values["int_quote_subheading"] = " ".join((post.get("quote_subheading") or "").split())[:MAX_SUBHEADING] or False
        if "quote_footer" in post:
            values["int_quote_footer"] = " ".join((post.get("quote_footer") or "").split())[:MAX_FOOTER] or False
        commercial = user.partner_id.commercial_partner_id
        if logo and logo[0]:
            # The logo is the company contact's image, the same one Documents shows.
            commercial._int_portal_set_logo(user, logo[0], logo[1])
        if values:
            commercial.sudo().write(values)
        return commercial
