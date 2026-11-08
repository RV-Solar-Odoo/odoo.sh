import { PaymentForm } from "@payment/interactions/payment_form";
import { patch } from "@web/core/utils/patch";

// Stripe Link texts a code as soon as the card form is built with a saved email.
// Card payments and saved cards do not use that prompt.
// Stripe.js exposes `elements` as a getter, so the instance cannot be patched
// by assignment. A proxy intercepts the call instead.
function bindMethod(target, value) {
    return typeof value === "function" ? value.bind(target) : value;
}

function elementsWithoutLink(elements) {
    return new Proxy(elements, {
        get(target, prop) {
            if (prop === "create") {
                const originalCreate = target.create.bind(target);
                return function createWithoutLink(type, elementOptions = {}) {
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
            }
            return bindMethod(target, Reflect.get(target, prop, target));
        },
    });
}

function stripeWithoutLink(OriginalStripe) {
    const wrapped = function stripeWithoutLinkCall(...stripeArgs) {
        const stripe = OriginalStripe(...stripeArgs);
        return new Proxy(stripe, {
            get(target, prop) {
                if (prop === "elements") {
                    const originalElements = target.elements.bind(target);
                    return function elementsCall(options) {
                        return elementsWithoutLink(originalElements(options));
                    };
                }
                return bindMethod(target, Reflect.get(target, prop, target));
            },
        });
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
