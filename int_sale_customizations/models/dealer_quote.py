import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

MAX_QTY = 9999
MAX_PRICE = 10000000
MAX_NAME = 120
MAX_NOTES = 4000
CUSTOMER_PRICE_KEYS = ("id", "name", "sku", "price", "map_missing")

_NAME_RE = re.compile(r"^Q(\d+)$")


def _int_clean_text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _int_clean_notes(value, limit):
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _int_clean_number(value, default=0.0, lowest=0.0, highest=MAX_PRICE):
    try:
        number = float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    if number < lowest:
        return lowest
    return min(number, highest)


def _int_clean_date(value):
    if not value:
        return False
    try:
        return fields.Date.to_date(str(value).strip())
    except (ValueError, TypeError):
        return False


class IntDealerQuote(models.Model):
    """A price a dealer gives their own customer.

    The customer pays MAP or MSRP (or a price the dealer typed). The dealer's
    wholesale cost is only for the margin on this screen. It is never part of
    the product search payload.
    """

    _name = "int.dealer.quote"
    _description = "Customer quote"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, copy=False)
    partner_id = fields.Many2one(
        "res.partner", string="Dealer", required=True, index=True, ondelete="restrict",
    )
    user_id = fields.Many2one("res.users", string="Created by", ondelete="set null")
    company_id = fields.Many2one("res.company", required=True, index=True)
    currency_id = fields.Many2one("res.currency", required=True)
    customer_name = fields.Char(string="Customer", required=True)
    customer_email = fields.Char(string="Email")
    customer_phone = fields.Char(string="Phone")
    customer_address_id = fields.Many2one(
        "res.partner", string="Customer address", ondelete="set null",
    )
    price_basis = fields.Selection(
        [("map", "MAP"), ("msrp", "MSRP")],
        string="Customer price",
        required=True,
        default="map",
    )
    line_ids = fields.One2many("int.dealer.quote.line", "quote_id", string="Lines", copy=True)
    notes = fields.Text(string="Memo")
    valid_until = fields.Date(string="Valid until")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("sent", "Sent"),
            ("accepted", "Accepted"),
            ("converted", "Converted"),
        ],
        default="draft",
        required=True,
        copy=False,
    )
    amount_untaxed = fields.Monetary(compute="_compute_amount_untaxed")
    margin_amount = fields.Monetary(compute="_compute_margin_amount", string="Product margin")

    @api.depends("line_ids.unit_price", "line_ids.quantity")
    def _compute_amount_untaxed(self):
        for quote in self:
            quote.amount_untaxed = sum(line.unit_price * line.quantity for line in quote.line_ids)

    @api.depends(
        "line_ids.unit_price", "line_ids.quantity", "line_ids.line_type", "line_ids.product_id",
    )
    def _compute_margin_amount(self):
        for quote in self:
            total = 0.0
            for line in quote.line_ids:
                if line.line_type != "product":
                    continue
                total += (line.unit_price - line.dealer_cost) * line.quantity
            quote.margin_amount = total

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            partner = self.env["res.partner"].browse(vals.get("partner_id")).exists()
            commercial = partner.commercial_partner_id if partner else partner
            if commercial and vals.get("partner_id") != commercial.id:
                vals["partner_id"] = commercial.id
            if not vals.get("name") and commercial:
                vals["name"] = self._int_next_name(commercial)
            if vals.get("price_basis") not in ("map", "msrp"):
                basis = commercial.int_quote_price_basis if commercial else "map"
                vals["price_basis"] = basis if basis in ("map", "msrp") else "map"
            if not vals.get("valid_until"):
                vals["valid_until"] = fields.Date.context_today(self) + timedelta(days=30)
            if not vals.get("currency_id") and vals.get("company_id"):
                company = self.env["res.company"].browse(vals["company_id"])
                vals["currency_id"] = company.currency_id.id
        return super().create(vals_list)

    def _int_basis_label(self):
        self.ensure_one()
        return _("MSRP") if self.price_basis == "msrp" else _("MAP")

    # Lookups. The domain is built from the user before any sudo().

    @api.model
    def _int_domain(self, user, company):
        commercial = user.partner_id.commercial_partner_id
        return [("partner_id", "=", commercial.id), ("company_id", "=", company.id)]

    @api.model
    def _int_for_user(self, user, company, quote_id=None):
        if not user or user._is_public() or not company:
            return self.browse()
        if user.share and not user.int_portal_can("create_quotes"):
            return self.browse()
        domain = self._int_domain(user, company)
        if quote_id not in (None, False, ""):
            try:
                domain.append(("id", "=", int(quote_id)))
            except (TypeError, ValueError):
                return self.browse()
        return self.sudo().search(domain)

    def _int_visible_to(self, user, company):
        self.ensure_one()
        if not user or user._is_public() or not company or self.company_id != company:
            return False
        if user.has_group("base.group_user"):
            return True
        return self.partner_id == user.partner_id.commercial_partner_id

    @api.model
    def _int_check_editor(self, user):
        if not user or user._is_public() or not user.int_portal_can("create_quotes"):
            raise UserError(_("You cannot change customer quotes."))

    @api.model
    def _int_next_name(self, commercial):
        numbers = []
        for name in self.sudo().search([("partner_id", "=", commercial.id)]).mapped("name"):
            match = _NAME_RE.match(name or "")
            if match:
                numbers.append(int(match.group(1)))
        return "Q%04d" % (max(numbers, default=0) + 1)

    @api.model
    def _int_customer_addresses(self, commercial):
        return commercial.child_ids.filtered(lambda partner: partner.int_address_category == "customer")

    @api.model
    def _int_customer_address(self, commercial, address_id):
        try:
            address_id = int(address_id)
        except (TypeError, ValueError):
            return self.env["res.partner"]
        return self._int_customer_addresses(commercial).filtered(lambda partner: partner.id == address_id)[:1]

    @api.model
    def _int_create(self, user, company, customer_name, email=None, phone=None):
        self._int_check_editor(user)
        name = _int_clean_text(customer_name, MAX_NAME)
        if not name:
            raise UserError(_("Enter the customer's name."))
        commercial = user.partner_id.commercial_partner_id
        basis = commercial.int_quote_price_basis if commercial.int_quote_price_basis in ("map", "msrp") else "map"
        return self.sudo().create({
            "name": self._int_next_name(commercial),
            "partner_id": commercial.id,
            "user_id": user.id,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "customer_name": name,
            "customer_email": _int_clean_text(email, MAX_NAME),
            "customer_phone": _int_clean_text(phone, 40),
            "price_basis": basis,
        })

    def _int_has_amount(self, amount):
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        if not currency:
            return (amount or 0.0) > 0
        return currency.compare_amounts(amount or 0.0, 0.0) > 0

    def _int_customer_price(self, product):
        """(price the customer pays, True when MAP was missing and MSRP was used)."""
        self.ensure_one()
        template = product.sudo().product_tmpl_id
        msrp = template.list_price or 0.0
        if "map_price" in template._fields:
            map_amount = template.map_price or 0.0
        else:
            map_amount = 0.0
        missing = self.price_basis == "map" and not self._int_has_amount(map_amount)
        if self.price_basis == "msrp" or missing:
            return msrp, missing
        return map_amount, False

    def _int_wholesale(self, product, quantity):
        """What this dealer pays. Never send this to the customer's quote."""
        self.ensure_one()
        product = product.sudo()
        partner = self.partner_id.sudo().with_company(self.company_id)
        pricelist = partner.property_product_pricelist
        qty = quantity or 1.0
        if not pricelist:
            return product.product_tmpl_id.list_price or 0.0
        kwargs = {
            "quantity": qty,
            "currency": self.currency_id or self.company_id.currency_id,
        }
        if "uom_id" in product._fields and product.uom_id:
            kwargs["uom"] = product.uom_id
        return pricelist._get_product_price(product, **kwargs)

    def _int_product_choice(self, product):
        self.ensure_one()
        price, missing = self._int_customer_price(product)
        choice = {
            "id": product.id,
            "name": product.sudo().with_context(display_default_code=False).display_name,
            "sku": product.sudo().default_code or "",
            "price": price,
            "map_missing": missing,
        }
        return {key: choice[key] for key in CUSTOMER_PRICE_KEYS}

    @api.model
    def _int_find_products(self, company, term, website=None):
        term = " ".join(str(term or "").split())[:60]
        if len(term) < 2 or not company:
            return self.env["product.product"]
        candidates = self.env["product.product"].sudo().search([
            ("sale_ok", "=", True),
            ("company_id", "in", [company.id, False]),
            "|", ("name", "ilike", term), ("default_code", "ilike", term),
        ], limit=30)
        SaleOrder = self.env["sale.order"]
        return candidates.filtered(
            lambda product: SaleOrder._int_product_on_website(product, website)
        )[:8]

    def _int_sellable_product(self, product_id, website):
        self.ensure_one()
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            raise UserError(_("That product is not available.")) from None
        product = self.env["product.product"].sudo().browse(product_id).exists()
        if not product or not self.env["sale.order"]._int_product_on_website(product, website):
            raise UserError(_("That product is not available."))
        if product.company_id and product.company_id != self.company_id:
            raise UserError(_("That product is not available."))
        return product

    def _int_add_product(self, product):
        self.ensure_one()
        existing = self.line_ids.filtered(
            lambda line: line.line_type == "product" and line.product_id == product
        )[:1]
        if existing:
            existing.quantity += 1
            return existing
        price, _missing = self._int_customer_price(product)
        return self.env["int.dealer.quote.line"].sudo().create({
            "quote_id": self.id,
            "line_type": "product",
            "product_id": product.id,
            "name": product.sudo().with_context(display_default_code=False).display_name,
            "quantity": 1,
            "unit_price": price,
            "sequence": self._int_next_sequence(),
        })

    def _int_add_custom(self, description, quantity, price):
        self.ensure_one()
        description = _int_clean_text(description, 240)
        if not description:
            raise UserError(_("Describe the labor or other charge."))
        qty = _int_clean_number(quantity, default=1.0, highest=MAX_QTY)
        if qty <= 0:
            qty = 1.0
        return self.env["int.dealer.quote.line"].sudo().create({
            "quote_id": self.id,
            "line_type": "custom",
            "name": description,
            "quantity": qty,
            "unit_price": _int_clean_number(price),
            "price_manual": True,
            "sequence": self._int_next_sequence(),
        })

    def _int_next_sequence(self):
        self.ensure_one()
        sequences = self.line_ids.mapped("sequence")
        return (max(sequences) if sequences else 0) + 10

    def _int_apply(self, user, post, website=None):
        """Save the editor. Checks the product before any write.

        Posted line prices are applied first. A line whose price still matches
        the old basis stays automatic, so a basis change on the same save can
        reprice it. A typed price stays.
        """
        self.ensure_one()
        self._int_check_editor(user)
        if not self._int_visible_to(user, self.company_id):
            raise UserError(_("This quote is not on your account."))
        product = self.env["product.product"]
        if post.get("add_product"):
            product = self._int_sellable_product(post.get("product_id"), website)
        description = ""
        if "custom_description" in post:
            description = _int_clean_text(post.get("custom_description"), 240)
        if post.get("intent") == "custom" and not description:
            raise UserError(_("Describe the labor or other charge."))
        custom = None
        if description:
            custom = (description, post.get("custom_quantity"), post.get("custom_price"))
        basis = post.get("price_basis") or self.price_basis
        if basis not in ("map", "msrp"):
            raise UserError(_("Choose MAP or MSRP."))

        quote = self.sudo()
        values = {}
        if "customer_name" in post:
            customer_name = _int_clean_text(post.get("customer_name"), MAX_NAME)
            if customer_name:
                values["customer_name"] = customer_name
        if "customer_email" in post:
            values["customer_email"] = _int_clean_text(post.get("customer_email"), MAX_NAME)
        if "customer_phone" in post:
            values["customer_phone"] = _int_clean_text(post.get("customer_phone"), 40)
        if "notes" in post:
            values["notes"] = _int_clean_notes(post.get("notes"), MAX_NOTES)
        if "customer_address_id" in post:
            values["customer_address_id"] = self._int_customer_address(
                quote.partner_id, post.get("customer_address_id"),
            ).id
        if values:
            quote.write(values)
        valid_until = _int_clean_date(post.get("valid_until")) if "valid_until" in post else False
        if valid_until:
            quote.valid_until = valid_until
        quote._int_apply_lines(post)
        if basis != quote.price_basis:
            quote.price_basis = basis
            quote.line_ids.filtered(
                lambda line: line.line_type == "product" and not line.price_manual
            )._int_set_customer_price()
        if product:
            quote._int_add_product(product)
        if custom:
            quote._int_add_custom(*custom)
        return quote

    def _int_apply_lines(self, post):
        for line in list(self.line_ids):
            if post.get("remove_%s" % line.id):
                line.unlink()
                continue
            qty_key = "qty_%s" % line.id
            if qty_key in post:
                qty = _int_clean_number(post.get(qty_key), default=line.quantity, highest=MAX_QTY)
                if qty <= 0:
                    line.unlink()
                    continue
                line.quantity = qty
            price_key = "price_%s" % line.id
            if price_key in post:
                line._int_update_price(post.get(price_key))


class IntDealerQuoteLine(models.Model):
    _name = "int.dealer.quote.line"
    _description = "Customer quote line"
    _order = "sequence, id"

    quote_id = fields.Many2one(
        "int.dealer.quote", required=True, index=True, ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    line_type = fields.Selection(
        [("product", "Product"), ("custom", "Labor or other")],
        required=True,
        default="product",
    )
    product_id = fields.Many2one("product.product", ondelete="restrict")
    name = fields.Char(required=True)
    quantity = fields.Float(default=1.0, digits="Product Unit")
    unit_price = fields.Monetary(string="Customer price")
    price_manual = fields.Boolean(
        string="Price edited",
        help="Set when the dealer types a price, so a MAP/MSRP change does not overwrite it.",
    )
    currency_id = fields.Many2one(related="quote_id.currency_id", store=True)
    price_subtotal = fields.Monetary(compute="_compute_price_subtotal")
    map_price = fields.Monetary(compute="_compute_reference")
    msrp_price = fields.Monetary(compute="_compute_reference")
    dealer_cost = fields.Monetary(
        compute="_compute_reference",
        help="What the dealer pays. Shown on the quote screen only.",
    )
    map_missing = fields.Boolean(compute="_compute_price_flags")
    below_map = fields.Boolean(compute="_compute_price_flags")

    @api.depends("unit_price", "quantity")
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = (line.unit_price or 0.0) * (line.quantity or 0.0)

    @api.depends(
        "line_type", "product_id", "quantity",
        "quote_id.partner_id", "quote_id.company_id", "quote_id.currency_id",
    )
    def _compute_reference(self):
        for line in self:
            product = line.product_id
            if line.line_type != "product" or not product or not line.quote_id:
                line.map_price = 0.0
                line.msrp_price = 0.0
                line.dealer_cost = 0.0
                continue
            template = product.sudo().product_tmpl_id
            line.msrp_price = template.list_price or 0.0
            if "map_price" in template._fields:
                line.map_price = template.map_price or 0.0
            else:
                line.map_price = 0.0
            line.dealer_cost = line.quote_id._int_wholesale(product, line.quantity)

    @api.depends("line_type", "unit_price", "map_price", "quote_id.price_basis", "quote_id.currency_id")
    def _compute_price_flags(self):
        for line in self:
            quote = line.quote_id
            currency = quote.currency_id
            has_map = bool(currency and currency.compare_amounts(line.map_price or 0.0, 0.0) > 0)
            line.map_missing = line.line_type == "product" and quote.price_basis == "map" and not has_map
            line.below_map = (
                line.line_type == "product"
                and has_map
                and currency.compare_amounts(line.unit_price or 0.0, line.map_price) < 0
            )

    @api.constrains("line_type", "product_id", "name")
    def _check_line(self):
        for line in self:
            if line.line_type == "product" and not line.product_id:
                raise ValidationError(_("A product line needs a product."))
            if line.line_type == "custom" and not line.name:
                raise ValidationError(_("Describe the labor or other charge."))

    def _int_set_customer_price(self):
        for line in self:
            if line.line_type != "product" or line.price_manual or not line.product_id:
                continue
            price, _missing = line.quote_id._int_customer_price(line.product_id)
            line.unit_price = price

    def _int_update_price(self, raw):
        self.ensure_one()
        price = _int_clean_number(raw)
        self.unit_price = price
        if self.line_type != "product" or not self.product_id:
            self.price_manual = True
            return
        expected, _missing = self.quote_id._int_customer_price(self.product_id)
        currency = self.quote_id.currency_id
        same = currency.compare_amounts(price, expected) == 0 if currency else price == expected
        self.price_manual = not same

    def _int_margin_percent(self):
        self.ensure_one()
        if self.line_type != "product" or not self.unit_price:
            return 0.0
        return (self.unit_price - self.dealer_cost) / self.unit_price * 100.0

    def _int_margin_label(self):
        """Whole-number margin, such as 33%. The template prints this string.

        A percent sign inside a QWeb expression is compiled as a format string,
        so the page cannot format the number itself.
        """
        self.ensure_one()
        return f"{round(self._int_margin_percent())}%"

    def _int_subtotal(self):
        self.ensure_one()
        return self.unit_price * self.quantity
