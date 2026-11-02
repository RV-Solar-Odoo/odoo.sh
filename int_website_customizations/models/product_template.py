from odoo import models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _int_map_amount(self):
        self.ensure_one()
        if "map_price" not in self._fields:
            return 0.0
        return self.map_price or 0.0

    def _int_is_dealer_pricelist(self, pricelist, website):
        """A dealer list has its own rules. The public Default list does not."""
        del website
        return bool(pricelist and pricelist.item_ids)

    def _int_website_selling_price(self, pricelist_price, pricelist, website):
        """Website unit price: MAP for the public, the pricelist for a dealer.

        Returns ``(selling, msrp, map_price, dealer)`` before tax.
        """
        self.ensure_one()
        msrp = self.list_price or 0.0
        map_price = self._int_map_amount() or msrp
        dealer = self._int_is_dealer_pricelist(pricelist, website)
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
        if not template._int_map_amount() and not self._int_is_dealer_pricelist(request.pricelist, website):
            return info

        pricelist = request.pricelist.with_context(self.env.context)
        currency = website.currency_id
        pricelist_price, _rule = pricelist._get_product_price_rule(
            product=product_or_template,
            quantity=quantity,
            uom=uom,
            currency=currency,
        )
        selling, msrp, map_price, dealer = template._int_website_selling_price(
            pricelist_price, request.pricelist, website
        )
        taxed_selling = self._int_taxed_website_price(selling, website, product_or_template)
        taxed_msrp = self._int_taxed_website_price(msrp, website, product_or_template)
        taxed_map = self._int_taxed_website_price(map_price, website, product_or_template)
        info.update({
            "price": taxed_selling,
            "list_price": taxed_msrp,
            "has_discounted_price": currency.compare_amounts(taxed_msrp, taxed_selling) == 1,
            "int_msrp": taxed_msrp,
            "int_map_price": taxed_map,
            "int_dealer_price": taxed_selling if dealer else False,
            "int_is_dealer": dealer,
            "int_show_price_breakdown": True,
        })
        return info

    def _get_sales_prices(self, website):
        """Shop cards: slash the sales price, show MAP or the dealer price."""
        res = super()._get_sales_prices(website)
        if not self:
            return res
        pricelist = request.pricelist
        raw_prices = pricelist._compute_price_rule(self, 1.0)
        currency = website.currency_id
        for template in self:
            if template.id not in res:
                continue
            pricelist_price = raw_prices[template.id][0]
            selling, msrp, _map_price, _dealer = template._int_website_selling_price(
                pricelist_price, pricelist, website
            )
            if not template._int_map_amount() and not _dealer:
                continue
            res[template.id]["price_reduce"] = template._int_taxed_website_price(selling, website)
            if currency.compare_amounts(msrp, selling) == 1:
                res[template.id]["base_price"] = template._int_taxed_website_price(msrp, website)
            else:
                res[template.id].pop("base_price", None)
        return res
