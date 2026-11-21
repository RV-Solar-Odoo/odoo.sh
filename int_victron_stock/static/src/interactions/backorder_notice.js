import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { WebsiteSale } from "@website_sale/interactions/website_sale";

// The product page carries data-int-backorder="1" when the chosen quantity, on top of
// what is already in the cart, is more than we and Victron have. The flag is refreshed
// from the combination info each time the variant or quantity changes.
function isBackorder(el) {
    const wrapper = el.closest("#o_wsale_cta_wrapper") || el.closest(".js_product")?.querySelector("#o_wsale_cta_wrapper");
    return wrapper?.dataset.intBackorder === "1";
}

patch(WebsiteSale.prototype, {
    async _addToCart(el) {
        if (isBackorder(el)) {
            const confirmed = await new Promise((resolve) => {
                this.services.dialog.add(
                    ConfirmationDialog,
                    {
                        title: _t("This item is on backorder"),
                        body: _t(
                            "Some or all of this quantity is out of stock with us and our supplier, " +
                            "and there's no ETA yet. You won't be charged for the backordered part today. " +
                            "We'll invoice you once it arrives at our warehouse, before it ships."
                        ),
                        confirmLabel: _t("Add to Cart"),
                        confirm: () => resolve(true),
                        cancel: () => resolve(false),
                    },
                    { onClose: () => resolve(false) }
                );
            });
            if (!confirmed) {
                return;
            }
        }
        return super._addToCart(...arguments);
    },
});
