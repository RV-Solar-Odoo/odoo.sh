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

function bind(form) {
    const order = form.querySelector(".js-int-help-order");
    const product = form.querySelector(".js-int-help-product");
    const productText = form.querySelector("[name='product_text']");
    if (!order || !product) {
        return;
    }
    const load = () => {
        const orderId = order.value;
        if (!orderId) {
            fillProducts(product, [], "");
            return;
        }
        fetch(`/my/help/order-lines/${orderId}`, {
            headers: {Accept: "application/json"},
            credentials: "same-origin",
        })
            .then((response) => (response.ok ? response.json() : {lines: []}))
            .then((payload) => {
                fillProducts(product, payload.lines || [], product.dataset.selected || "");
                product.dataset.selected = "";
            })
            .catch(() => fillProducts(product, [], ""));
    };
    order.addEventListener("change", () => {
        product.dataset.selected = "";
        load();
    });
    product.addEventListener("change", () => {
        if (!productText || !product.value) {
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
