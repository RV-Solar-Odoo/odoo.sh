from odoo import models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _int_map_amount(self):
        self.ensure_one()
        if "map_price" not in self._fields:
            return 0.0
        return self.map_price or 0.0

    def _int_pricing_partner(self, website, order=None):
        """The contact whose pricelist decides MAP vs dealer pricing."""
        del website
        if order:
            return order.partner_id.sudo().commercial_partner_id
        ctx_id = self.env.context.get("int_pricing_partner_id")
        if ctx_id:
            return self.env["res.partner"].browse(ctx_id).sudo().commercial_partner_id
        if request:
            return request.env.user.partner_id.sudo().commercial_partner_id
        return self.env.user.partner_id.sudo().commercial_partner_id

    def _int_contact_pricelist(self, partner, website):
        if not partner:
            return self.env["product.pricelist"]
        company = website.company_id if website else self.env.company
        return partner.sudo().commercial_partner_id.with_company(company).property_product_pricelist

    def _int_public_pricelist(self, website):
        public_partner = self.env.ref("base.public_user").sudo().partner_id
        return self._int_contact_pricelist(public_partner, website)

    def _int_is_dealer_contact(self, partner, website):
        """A dealer is a contact whose pricelist is not the public default."""
        if not partner:
            return False
        partner = partner.sudo().commercial_partner_id
        public_partner = self.env.ref("base.public_user").sudo().partner_id.commercial_partner_id
        if partner == public_partner:
            return False
        if not self.env.context.get("int_pricing_partner_id") and request and request.env.user._is_public():
            return False
        pl = self._int_contact_pricelist(partner, website)
        public_pl = self._int_public_pricelist(website)
        return bool(pl) and bool(public_pl) and pl != public_pl

    def _int_website_selling_price(self, pricelist_price, partner, website):
        """Website unit price: MAP for retail, the contact pricelist for a dealer.

        Returns ``(selling, msrp, map_price, dealer)`` before tax.
        """
        self.ensure_one()
        msrp = self.list_price or 0.0
        map_price = self._int_map_amount() or msrp
        dealer = self._int_is_dealer_contact(partner, website)
        selling = pricelist_price if dealer else map_price
        return selling, msrp, map_price, dealer

    def _int_taxed_website_price(self, amount, website, product_or_template=None):
        self.ensure_one()
        product = product_or_template or self
        product_taxes = product.sudo().taxes_id._filter_taxes_by_company(self.env.company)
        fiscal = getattr(request, "fiscal_position", None) if request else None
        taxes = fiscal.map_tax(product_taxes) if fiscal and product_taxes else product_taxes
        return self._apply_taxes_to_price(
            amount,
            website.currency_id,
            product_taxes,
            taxes,
            product,
            website=website,
        )

    def _get_additionnal_combination_info(self, product_or_template, quantity, uom, date, website):
        """Sell the website at MAP, and keep the sales price as the struck MSRP."""
        info = super()._get_additionnal_combination_info(
            product_or_template, quantity, uom, date, website
        )
        if info.get("prevent_zero_price_sale"):
            return info
        template = (
            product_or_template.product_tmpl_id
            if product_or_template.is_product_variant
            else product_or_template
        )
        partner = template._int_pricing_partner(website)
        dealer = template._int_is_dealer_contact(partner, website)
        if not template._int_map_amount() and not dealer:
            return info

        contact_pl = template._int_contact_pricelist(partner, website) if dealer else request.pricelist
        pricelist = contact_pl.with_context(self.env.context)
        currency = website.currency_id
        pricelist_price, _rule = pricelist._get_product_price_rule(
            product=product_or_template,
            quantity=quantity,
            uom=uom,
            currency=currency,
        )
        selling, msrp, map_price, dealer = template._int_website_selling_price(
            pricelist_price, partner, website
        )
        taxed_selling = self._int_taxed_website_price(selling, website, product_or_template)
        taxed_msrp = self._int_taxed_website_price(msrp, website, product_or_template)
        info.update({
            "price": taxed_selling,
            "list_price": taxed_msrp,
            "has_discounted_price": currency.compare_amounts(taxed_msrp, taxed_selling) == 1,
            "int_is_dealer": dealer,
            "int_msrp": taxed_msrp,
            "int_map_price": self._int_taxed_website_price(map_price, website, product_or_template),
            "int_dealer_price": taxed_selling,
        })
        return info

    def _get_sales_prices(self, website):
        """Shop cards: slash the sales price, show MAP or the dealer price."""
        res = super()._get_sales_prices(website)
        if not self:
            return res
        partner = self._int_pricing_partner(website)
        dealer = self[:1]._int_is_dealer_contact(partner, website)
        pricelist = (
            self[:1]._int_contact_pricelist(partner, website) if dealer else request.pricelist
        )
        raw_prices = pricelist._compute_price_rule(self, 1.0)
        currency = website.currency_id
        for template in self:
            if template.id not in res:
                continue
            pricelist_price = raw_prices[template.id][0]
            selling, msrp, _map_price, _dealer = template._int_website_selling_price(
                pricelist_price, partner, website
            )
            if not template._int_map_amount() and not _dealer:
                continue
            res[template.id]["price_reduce"] = template._int_taxed_website_price(selling, website)
            if currency.compare_amounts(msrp, selling) == 1:
                res[template.id]["base_price"] = template._int_taxed_website_price(msrp, website)
            else:
                res[template.id].pop("base_price", None)
        return res
