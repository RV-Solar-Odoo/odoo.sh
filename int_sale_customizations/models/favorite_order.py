from odoo import _, api, fields, models
from odoo.exceptions import UserError

MAX_NAME = 120
MAX_QTY = 9999


def _int_number(value):
    """2.0 -> '2', 2.5 -> '2.5'."""
    return f"{value:g}"


class IntFavoriteOrder(models.Model):
    """A dealer's saved list of products, reordered from My Orders.

    Copied from an order or a cart when it is saved, so editing it never touches
    the order. Shared by every login of the dealer (the commercial partner) on
    one company's website.
    """

    _name = "int.favorite.order"
    _description = "Favorite order"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one(
        "res.partner", string="Dealer", required=True, index=True, ondelete="cascade",
        help="The commercial partner. Every login of this dealer shares the favorite.",
    )
    company_id = fields.Many2one(
        "res.company", required=True, index=True, default=lambda self: self.env.company,
    )
    source_order_id = fields.Many2one("sale.order", string="From order", index=True, ondelete="set null")
    line_ids = fields.One2many("int.favorite.order.line", "favorite_id", string="Products", copy=True)
    item_count = fields.Float(compute="_compute_item_count")

    @api.depends("line_ids.quantity")
    def _compute_item_count(self):
        for favorite in self:
            favorite.item_count = sum(favorite.line_ids.mapped("quantity"))

    def _int_count_label(self):
        """'7 items', without a trailing .0."""
        self.ensure_one()
        return _("%(count)s items", count=_int_number(self.item_count))

    # Lookups. The domain is built from the user before any sudo().

    @api.model
    def _int_domain(self, user, company):
        commercial = user.partner_id.commercial_partner_id
        return [("partner_id", "=", commercial.id), ("company_id", "=", company.id)]

    @api.model
    def _int_for_user(self, user, company, favorite_id=None, active=True):
        domain = self._int_domain(user, company)
        if favorite_id is not None:
            domain.append(("id", "=", int(favorite_id)))
        if active is not None:
            domain.append(("active", "=", active))
        return self.sudo().with_context(active_test=False).search(domain)

    @api.model
    def _int_by_order(self, user, company, orders):
        """{order id: favorite} for the given orders that are favorites."""
        if not orders:
            return {}
        favorites = self.sudo().search(
            self._int_domain(user, company) + [("source_order_id", "in", orders.ids)]
        )
        return {favorite.source_order_id.id: favorite for favorite in favorites}

    @api.model
    def _int_notice(self, user, company, params):
        """The "Saved" / "Removed · Undo" line after a favorite changes, from the URL."""
        if not user or user._is_public():
            return False
        for key, kind in (("int_fav_saved", "saved"), ("int_fav_removed", "removed")):
            value = str(params.get(key) or "")
            if value.isdigit():
                favorite = self._int_for_user(user, company, int(value), active=None)
                if favorite:
                    return {"kind": kind, "favorite": favorite}
        return False

    @api.model
    def _int_limit(self, company):
        return company.sudo().int_max_favorites or 25

    @api.model
    def _int_check_can_edit(self, user):
        if not user or user._is_public() or not user.int_portal_can("pin_orders"):
            raise UserError(_("You cannot change favorite orders."))

    @api.model
    def _int_check_limit(self, user, company):
        limit = self._int_limit(company)
        count = self.sudo().search_count(self._int_domain(user, company) + [("active", "=", True)])
        if count >= limit:
            raise UserError(_(
                "You can save up to %(limit)s favorite orders. Delete one first.", limit=limit,
            ))

    @api.model
    def _int_clean_name(self, name, fallback):
        name = " ".join((name or "").split())[:MAX_NAME]
        return name or fallback

    @api.model
    def _int_clean_qty(self, value, default=1.0):
        try:
            qty = float(value)
        except (TypeError, ValueError):
            return default
        if qty != qty:  # NaN
            return default
        return min(max(qty, 0.0), MAX_QTY)

    # Creating

    @api.model
    def _int_create_record(self, commercial, company, name, items, source_order=None):
        """Create without user checks. ``items`` is [(product, quantity)];
        the same product twice is merged."""
        merged = {}
        for product, qty in items:
            if product and qty > 0:
                merged[product] = merged.get(product, 0.0) + qty
        if not merged:
            raise UserError(_("There are no products to save."))
        return self.sudo().create({
            "name": name,
            "partner_id": commercial.id,
            "company_id": company.id,
            "source_order_id": source_order.id if source_order else False,
            "line_ids": [
                (0, 0, {"product_id": product.id, "quantity": qty, "sequence": index})
                for index, (product, qty) in enumerate(merged.items())
            ],
        })

    @api.model
    def _int_lines_to_items(self, order_lines):
        items = []
        for line in order_lines.filtered(lambda item: item._int_is_favorite_line()):
            qty = line.product_uom_id._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
            items.append((line.product_id, qty))
        return items

    @api.model
    def _int_create_from_order(self, user, company, order, name=None):
        self._int_check_can_edit(user)
        if not order or not order._int_owned_by(user):
            raise UserError(_("You cannot save this order."))
        existing = self._int_by_order(user, company, order).get(order.id)
        if existing:
            return existing
        self._int_check_limit(user, company)
        order = order.sudo()
        return self._int_create_record(
            user.partner_id.commercial_partner_id,
            company,
            self._int_clean_name(name, order.name),
            self._int_lines_to_items(order.order_line),
            source_order=order,
        )

    @api.model
    def _int_create_from_cart(self, user, company, cart, name=None):
        self._int_check_can_edit(user)
        if not cart or cart.state != "draft":
            raise UserError(_("Your cart is empty."))
        if cart.partner_id.commercial_partner_id != user.partner_id.commercial_partner_id:
            raise UserError(_("You cannot save this cart."))
        self._int_check_limit(user, company)
        fallback = _("Saved cart %(date)s", date=fields.Date.to_string(fields.Date.context_today(self)))
        return self._int_create_record(
            user.partner_id.commercial_partner_id,
            company,
            self._int_clean_name(name, fallback),
            self._int_lines_to_items(cart.sudo().order_line),
        )

    # Changing

    def _int_apply_edit(self, user, name=None, quantities=None, removed=None, added=None, website=None):
        """Rename, change quantities, remove lines, and add products.

        ``quantities`` {line id: qty}, ``removed`` line ids, ``added`` {product id: qty}.
        Lines and products that do not belong here are ignored.
        """
        self.ensure_one()
        self._int_check_can_edit(user)
        favorite = self.sudo()
        if name is not None:
            favorite.name = self._int_clean_name(name, favorite.name)
        removed = set(removed or ())
        for line in favorite.line_ids:
            if line.id in removed:
                continue
            if quantities and line.id in quantities:
                qty = self._int_clean_qty(quantities[line.id], line.quantity)
                if qty <= 0:
                    removed.add(line.id)
                else:
                    line.quantity = qty
        favorite.line_ids.filtered(lambda line: line.id in removed).unlink()
        SaleOrder = self.env["sale.order"]
        next_sequence = max(favorite.line_ids.mapped("sequence"), default=0) + 1
        for product_id, qty in (added or {}).items():
            product = self.env["product.product"].sudo().browse(int(product_id)).exists()
            qty = self._int_clean_qty(qty, 1.0)
            if not product or qty <= 0 or not SaleOrder._int_product_on_website(product, website):
                continue
            line = favorite.line_ids.filtered(lambda item: item.product_id == product)[:1]
            if line:
                line.quantity = min(line.quantity + qty, MAX_QTY)
            else:
                self.env["int.favorite.order.line"].sudo().create({
                    "favorite_id": favorite.id,
                    "product_id": product.id,
                    "quantity": qty,
                    "sequence": next_sequence,
                })
                next_sequence += 1
        if not favorite.line_ids:
            raise UserError(_("A favorite needs at least one product. Delete the favorite instead."))
        return favorite

    def _int_archive(self, user):
        self._int_check_can_edit(user)
        self.sudo().active = False

    def _int_restore(self, user, company):
        self.ensure_one()
        self._int_check_can_edit(user)
        if self.active:
            return
        self._int_check_limit(user, company)
        self.sudo().active = True

    # Adding to the cart

    def _int_cart_plan(self, website, selected=None):
        """Products to add and the ones to explain first, at live prices.

        ``selected`` {line id: qty} limits the plan to those lines with those
        quantities; None takes every line at its saved quantity.
        """
        self.ensure_one()
        SaleOrder = self.env["sale.order"]
        addable = []
        skipped = []
        for line in self.sudo().line_ids:
            if selected is not None:
                if line.id not in selected:
                    continue
                qty = self._int_clean_qty(selected[line.id], line.quantity)
            else:
                qty = line.quantity
            if qty <= 0:
                continue
            product = line.product_id
            if SaleOrder._int_product_on_website(product, website):
                addable.append((product, qty))
            else:
                skipped.append((product.display_name, _("Not available")))
        return addable, skipped


class IntFavoriteOrderLine(models.Model):
    _name = "int.favorite.order.line"
    _description = "Favorite order product"
    _order = "sequence, id"

    favorite_id = fields.Many2one(
        "int.favorite.order", required=True, index=True, ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade")
    quantity = fields.Float(default=1.0, digits="Product Unit")

    def _int_qty_label(self):
        self.ensure_one()
        return _int_number(self.quantity)
