import { PaymentForm } from "@payment/interactions/payment_form";
import { patch } from "@web/core/utils/patch";

// Stripe Link texts a code as soon as the card form is built with a saved email.
// Card payments and saved cards do not use that prompt.
function stripeWithoutLink(OriginalStripe) {
    const wrapped = function stripeWithoutLinkCall(...stripeArgs) {
        const stripe = OriginalStripe(...stripeArgs);
        const originalElements = stripe.elements.bind(stripe);
        stripe.elements = function elementsWithoutLink(options) {
            const elements = originalElements(options);
            const originalCreate = elements.create.bind(elements);
            elements.create = function createWithoutLink(type, elementOptions = {}) {
                if (type === "payment") {
                    elementOptions = {
                        ...elementOptions,
                        wallets: {
                            ...(elementOptions.wallets || {}),
                            link: "never",
                        },
                    };
                }
                return originalCreate(type, elementOptions);
            };
            return elements;
        };
        return stripe;
    };
    Object.assign(wrapped, OriginalStripe);
    return wrapped;
}

patch(PaymentForm.prototype, {
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        const alreadyBuilt = this.stripeElements?.[paymentOptionId];
        if (providerCode !== "stripe" || flow === "token" || alreadyBuilt || !window.Stripe) {
            return super._prepareInlineForm(...arguments);
        }
        const originalStripe = window.Stripe;
        window.Stripe = stripeWithoutLink(originalStripe);
        try {
            return await super._prepareInlineForm(...arguments);
        } finally {
            window.Stripe = originalStripe;
        }
    },
});
