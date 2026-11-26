// Customer quote product search. The click posts the product id. The server
// prices the line at MAP or MSRP. This file never reads a wholesale price.

function intQuoteText(tag, className, text) {
    const el = document.createElement(tag);
    if (className) {
        el.className = className;
    }
    el.textContent = text;
    return el;
}

function intQuoteShowResults(form, products) {
    const list = form.querySelector(".js-int-quote-results");
    list.replaceChildren();
    if (!products.length) {
        list.appendChild(intQuoteText("li", "o_int_fav_noresult", "No products found."));
    }
    for (const product of products) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "o_int_fav_result";
        const img = document.createElement("img");
        img.alt = "";
        img.src = product.image || "";
        button.appendChild(img);
        const label = document.createElement("span");
        label.appendChild(intQuoteText("span", "", product.name || ""));
        if (product.sku) {
            label.appendChild(intQuoteText("small", "", `SKU ${product.sku}`));
        }
        if (product.map_missing) {
            label.appendChild(intQuoteText("small", "", "No MAP, using MSRP"));
        }
        button.appendChild(label);
        button.appendChild(intQuoteText("strong", "", product.price_label || ""));
        button.appendChild(intQuoteText("span", "o_int_fav_result_add", "Add"));
        button.addEventListener("click", () => {
            if (!product.id) {
                return;
            }
            form.querySelector(".js-int-quote-product").value = String(product.id);
            form.querySelector(".js-int-quote-add").value = "1";
            const custom = form.querySelector(".js-int-quote-custom");
            if (custom) {
                custom.value = "";
            }
            form.submit();
        });
        item.appendChild(button);
        list.appendChild(item);
    }
    list.classList.remove("d-none");
}

let intQuoteTimer = 0;
let intQuoteSeq = 0;

document.addEventListener("input", (ev) => {
    const search = ev.target.closest(".js-int-quote-search");
    if (!search) {
        return;
    }
    const form = search.closest(".js-int-quote-edit");
    const term = search.value.trim();
    window.clearTimeout(intQuoteTimer);
    if (term.length < 2) {
        form.querySelector(".js-int-quote-results").classList.add("d-none");
        return;
    }
    intQuoteTimer = window.setTimeout(async () => {
        const seq = ++intQuoteSeq;
        const quoteId = form.dataset.quoteId || "";
        try {
            const response = await fetch(
                `/my/customer-quotes/products?quote_id=${encodeURIComponent(quoteId)}&q=${encodeURIComponent(term)}`,
                { credentials: "same-origin", headers: { Accept: "application/json" } },
            );
            const data = await response.json();
            if (seq === intQuoteSeq) {
                intQuoteShowResults(form, data.products || []);
            }
        } catch {
            // Leave the list as it was; the person can type again.
        }
    }, 250);
});

document.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && ev.target.closest(".js-int-quote-search")) {
        ev.preventDefault();
    }
});
