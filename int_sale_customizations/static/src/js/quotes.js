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

// Live pricing on the quote editor. Switching MAP / MSRP swaps the customer price
// on every product line whose price wasn't typed by hand, and the line totals,
// customer total and margin follow quantity and price as they change. Nothing is
// saved until Save Quote; the server applies the same rules.

function intQuoteMoney(form, amount) {
    const digits = Number(form.dataset.currencyDigits || 2);
    const number = (Number(amount) || 0).toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    });
    const symbol = form.dataset.currencySymbol || "";
    // Same as Odoo's monetary widget: symbol and amount joined by a no-break space.
    return form.dataset.currencyPosition === "after" ? `${number} ${symbol}` : `${symbol} ${number}`;
}

function intQuoteBasis(form) {
    const checked = form.querySelector("input[name='price_basis']:checked");
    return checked ? checked.value : "map";
}

function intQuoteExpected(line, basis) {
    const map = Number(line.dataset.map) || 0;
    const msrp = Number(line.dataset.msrp) || 0;
    return basis === "map" && map > 0 ? map : msrp;
}

function intQuoteSame(a, b) {
    return Math.abs((Number(a) || 0) - (Number(b) || 0)) < 0.005;
}

function intQuoteRecompute(form) {
    const basis = intQuoteBasis(form);
    let total = 0;
    let margin = 0;
    for (const line of form.querySelectorAll(".js-int-quote-line")) {
        const qtyInput = line.querySelector(".js-int-quote-qty");
        const priceInput = line.querySelector(".js-int-quote-price");
        const removeInput = line.querySelector(".js-int-fav-remove-input");
        const qty = Math.max(0, Number(qtyInput && qtyInput.value) || 0);
        const price = Math.max(0, Number(priceInput && priceInput.value) || 0);
        const subtotal = qty * price;
        const subtotalEl = line.querySelector(".js-int-quote-subtotal");
        if (subtotalEl) {
            subtotalEl.textContent = intQuoteMoney(form, subtotal);
        }
        const removed = removeInput && removeInput.value === "1";
        if (!removed) {
            total += subtotal;
        }
        if (line.dataset.product !== "1") {
            continue;
        }
        const cost = Number(line.dataset.cost) || 0;
        if (!removed) {
            margin += (price - cost) * qty;
        }
        const marginEl = line.querySelector(".js-int-quote-margin");
        if (marginEl) {
            marginEl.textContent = price ? `${Math.round(((price - cost) / price) * 100)}%` : "0%";
        }
        const map = Number(line.dataset.map) || 0;
        const below = line.querySelector(".js-int-quote-below");
        if (below) {
            below.classList.toggle("d-none", !(map > 0 && price < map - 0.005));
        }
        const noMap = line.querySelector(".js-int-quote-nomap");
        if (noMap) {
            noMap.classList.toggle("d-none", !(basis === "map" && map <= 0));
        }
    }
    const totalEl = form.querySelector(".js-int-quote-total");
    if (totalEl) {
        totalEl.textContent = intQuoteMoney(form, total);
    }
    const marginTotalEl = form.querySelector(".js-int-quote-margin-total");
    if (marginTotalEl) {
        marginTotalEl.textContent = intQuoteMoney(form, margin);
    }
}

function intQuoteDirty(form) {
    const note = form.querySelector(".js-int-quote-dirty");
    if (note) {
        note.classList.remove("d-none");
    }
}

document.addEventListener("change", (ev) => {
    if (ev.target.name !== "price_basis") {
        return;
    }
    const form = ev.target.closest(".js-int-quote-edit");
    if (!form) {
        return;
    }
    const basis = intQuoteBasis(form);
    for (const line of form.querySelectorAll(".js-int-quote-line[data-product='1']")) {
        if (line.dataset.manual === "1") {
            continue;
        }
        const priceInput = line.querySelector(".js-int-quote-price");
        if (priceInput) {
            priceInput.value = intQuoteExpected(line, basis).toFixed(2);
        }
    }
    intQuoteRecompute(form);
    intQuoteDirty(form);
});

document.addEventListener("input", (ev) => {
    const form = ev.target.closest(".js-int-quote-edit");
    if (!form || ev.target.closest(".js-int-quote-search")) {
        return;
    }
    if (ev.target.classList.contains("js-int-quote-price")) {
        // A price that equals the MAP/MSRP price stays automatic; anything else was typed.
        const line = ev.target.closest(".js-int-quote-line");
        if (line && line.dataset.product === "1") {
            line.dataset.manual = intQuoteSame(ev.target.value, intQuoteExpected(line, intQuoteBasis(form))) ? "0" : "1";
        }
    }
    if (ev.target.closest(".js-int-quote-line")) {
        intQuoteRecompute(form);
    }
    intQuoteDirty(form);
});

// The − / + stepper and the bin (favorites.js) change values without an input
// event, so recompute after their click handlers have run.
document.addEventListener("click", (ev) => {
    if (!ev.target.closest("[data-int-step], .js-int-fav-remove")) {
        return;
    }
    const form = ev.target.closest(".js-int-quote-edit");
    if (!form) {
        return;
    }
    window.setTimeout(() => {
        intQuoteRecompute(form);
        intQuoteDirty(form);
    }, 0);
});
