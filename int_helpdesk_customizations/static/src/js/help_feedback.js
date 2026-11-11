/** @odoo-module **/

function fillProducts(select, lines, selected) {
    const current = selected || "";
    while (select.firstChild) {
        select.removeChild(select.firstChild);
    }
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select a product";
    select.appendChild(placeholder);
    for (const line of lines) {
        const option = document.createElement("option");
        option.value = String(line.product_id);
        option.textContent = line.name;
        if (String(line.product_id) === String(current)) {
            option.selected = true;
        }
        select.appendChild(option);
    }
}

// One serial on the delivered order is prefilled, several become a dropdown,
// none leaves the text box. Only one of the two inputs is enabled, so only
// that one is submitted.
function applySerials(form, serials) {
    const text = form.querySelector(".js-int-help-serial-text");
    const pick = form.querySelector(".js-int-help-serial-pick");
    if (!text || !pick) {
        return;
    }
    const list = serials || [];
    const several = list.length > 1;
    // Clear a serial we filled for the previous product; keep one the person typed.
    if (text.dataset.intPrefilled && text.value === text.dataset.intPrefilled) {
        text.value = "";
    }
    text.dataset.intPrefilled = "";
    pick.classList.toggle("d-none", !several);
    pick.disabled = !several;
    text.classList.toggle("d-none", several);
    text.disabled = several;
    while (pick.firstChild) {
        pick.removeChild(pick.firstChild);
    }
    if (several) {
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Select a serial number";
        pick.appendChild(placeholder);
        for (const serial of list) {
            const option = document.createElement("option");
            option.value = serial;
            option.textContent = serial;
            option.selected = serial === text.value;
            pick.appendChild(option);
        }
    } else if (list.length === 1) {
        text.value = list[0];
        text.dataset.intPrefilled = list[0];
    }
}

function bindToggles(form) {
    // "Other" boxes under the reason and outcome lists.
    form.querySelectorAll(".js-int-help-other").forEach((select) => {
        const wrap = form.querySelector(select.dataset.other);
        if (!wrap) {
            return;
        }
        const sync = () => wrap.classList.toggle("d-none", select.value !== "other");
        select.addEventListener("change", sync);
        sync();
    });
    // "Where did you buy it?": the dealer list is required only for "From one of our dealers".
    const dealerWrap = form.querySelector(".js-int-help-dealer");
    if (dealerWrap) {
        const dealer = dealerWrap.querySelector("select");
        const sync = () => {
            const picked = form.querySelector("input[name='purchase_source']:checked");
            const fromDealer = Boolean(picked) && picked.value === "dealer";
            dealerWrap.classList.toggle("d-none", !fromDealer);
            dealer.required = fromDealer;
        };
        form.querySelectorAll("input[name='purchase_source']").forEach((input) => {
            input.addEventListener("change", sync);
        });
        sync();
    }
}

function bind(form) {
    bindToggles(form);
    const order = form.querySelector(".js-int-help-order");
    const product = form.querySelector(".js-int-help-product");
    const productText = form.querySelector("[name='product_text']");
    if (!order || !product) {
        return;
    }
    // Return form: "My order isn't listed" swaps the product list for typed fields.
    const picked = form.querySelector(".js-int-help-picked");
    const typed = form.querySelector(".js-int-help-typed");
    const showTyped = (on) => {
        if (!picked || !typed) {
            return;
        }
        picked.classList.toggle("d-none", on);
        typed.classList.toggle("d-none", !on);
        product.required = !on;
        typed.querySelectorAll("input").forEach((input) => {
            input.required = on;
        });
    };
    let serialsByProduct = {};
    const syncSerials = () => {
        applySerials(form, serialsByProduct[product.value] || []);
    };
    const load = () => {
        const orderId = order.value;
        const isTyped = Boolean(order.dataset.typed) && orderId === order.dataset.typed;
        showTyped(isTyped);
        serialsByProduct = {};
        if (!orderId || isTyped) {
            fillProducts(product, [], "");
            syncSerials();
            return;
        }
        fetch(`/my/help/order-lines/${orderId}`, {
            headers: {Accept: "application/json"},
            credentials: "same-origin",
        })
            .then((response) => (response.ok ? response.json() : {lines: []}))
            .then((payload) => {
                const lines = payload.lines || [];
                serialsByProduct = {};
                for (const line of lines) {
                    serialsByProduct[String(line.product_id)] = line.serials || [];
                }
                fillProducts(product, lines, product.dataset.selected || "");
                product.dataset.selected = "";
                syncSerials();
            })
            .catch(() => {
                fillProducts(product, [], "");
                syncSerials();
            });
    };
    order.addEventListener("change", () => {
        product.dataset.selected = "";
        load();
    });
    product.addEventListener("change", syncSerials);
    product.addEventListener("change", () => {
        // Warranty copies the picked product into its text field; the return's typed field stays as typed.
        if (!productText || !product.value || productText.closest(".js-int-help-typed")) {
            return;
        }
        const option = product.selectedOptions[0];
        if (option) {
            productText.value = option.textContent.trim();
        }
    });
    if (order.value) {
        load();
    }
}

function splitName(full) {
    const parts = (full || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) {
        return ["", ""];
    }
    if (parts.length === 1) {
        return [parts[0], ""];
    }
    return [parts[0], parts.slice(1).join(" ")];
}

function fillIfEmpty(input, value) {
    if (input && !input.value && value) {
        input.value = value;
    }
}

function prefillWebsiteForms() {
    const nameMeta = document.querySelector('meta[name="int-contact-name"]');
    const emailMeta = document.querySelector('meta[name="int-contact-email"]');
    if (!nameMeta && !emailMeta) {
        return;
    }
    const [first, last] = splitName(nameMeta ? nameMeta.content : "");
    const email = emailMeta ? emailMeta.content.trim() : "";
    document.querySelectorAll('form[data-model_name="helpdesk.ticket"]').forEach((form) => {
        fillIfEmpty(form.querySelector('input[name="First Name"]'), first);
        fillIfEmpty(form.querySelector('input[name="Last Name"]'), last);
        fillIfEmpty(form.querySelector('input[name="partner_email"]'), email);
    });
}

function guardSubmit(form) {
    form.addEventListener("submit", (event) => {
        if (form.dataset.intSubmitting === "1") {
            event.preventDefault();
            return;
        }
        form.dataset.intSubmitting = "1";
        const button = form.querySelector('[type="submit"]');
        if (button) {
            window.setTimeout(() => {
                button.disabled = true;
            }, 0);
        }
    });
}

function start() {
    document.querySelectorAll(".o_int_help_form").forEach((form) => {
        bind(form);
        guardSubmit(form);
    });
    prefillWebsiteForms();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}
