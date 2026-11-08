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

function start() {
    document.querySelectorAll(".o_int_help_form").forEach(bind);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}
