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

// Live totals on the quote editor. Line totals, Products, Labor and charges, the
// customer total and the dealer's margin follow quantity and price as they change.
// Nothing is saved until Save Quote.

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

function intQuoteExpected(line, basis) {
    const map = Number(line.dataset.map) || 0;
    const msrp = Number(line.dataset.msrp) || 0;
    return basis === "map" && map > 0 ? map : msrp;
}

function intQuoteSame(a, b) {
    return Math.abs((Number(a) || 0) - (Number(b) || 0)) < 0.005;
}

function intQuoteSetAll(form, selector, text) {
    for (const el of form.querySelectorAll(selector)) {
        el.textContent = text;
    }
}

function intQuoteRecompute(form) {
    let products = 0;
    let charges = 0;
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
        if (line.dataset.product !== "1") {
            if (!removed) {
                charges += subtotal;
            }
            continue;
        }
        const cost = Number(line.dataset.cost) || 0;
        if (!removed) {
            products += subtotal;
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
    }
    intQuoteSetAll(form, ".js-int-quote-products", intQuoteMoney(form, products));
    intQuoteSetAll(form, ".js-int-quote-charges", intQuoteMoney(form, charges));
    intQuoteSetAll(form, ".js-int-quote-total", intQuoteMoney(form, products + charges));
    intQuoteSetAll(form, ".js-int-quote-margin-total", intQuoteMoney(form, margin));
}

function intQuoteDirty(form) {
    for (const note of form.querySelectorAll(".js-int-quote-dirty")) {
        note.classList.remove("d-none");
    }
}

document.addEventListener("input", (ev) => {
    const form = ev.target.closest(".js-int-quote-edit");
    if (!form || ev.target.closest(".js-int-quote-search") || ev.target.classList.contains("js-int-quote-dealer")) {
        return;
    }
    if (ev.target.classList.contains("js-int-quote-price")) {
        // A price that equals the quote's MAP/MSRP price stays automatic; anything else was typed.
        const line = ev.target.closest(".js-int-quote-line");
        if (line && line.dataset.product === "1") {
            const basis = form.dataset.basis || "map";
            line.dataset.manual = intQuoteSame(ev.target.value, intQuoteExpected(line, basis)) ? "0" : "1";
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

// Show Dealer Info: wholesale, margin and MAP notes stay hidden until the dealer
// turns this on, so a customer looking at the screen sees only their prices.
// It is off each time the page opens.
document.addEventListener("change", (ev) => {
    if (!ev.target.classList.contains("js-int-quote-dealer")) {
        return;
    }
    const form = ev.target.closest(".js-int-quote-edit");
    if (form) {
        form.classList.toggle("o_int_show_dealer", ev.target.checked);
    }
});

// Quote Settings: the preview follows the accent, subheading, footer and logo.

function intQsReadable(hex) {
    // Same rule as the PDF: darken until text reads on white (4.5:1).
    const lum = (h) => {
        const c = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
            .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    };
    let color = /^#[0-9a-f]{6}$/i.test(hex) ? hex.toLowerCase() : "#1f2433";
    for (let i = 0; i < 20 && 1.05 / (lum(color) + 0.05) < 4.5; i++) {
        color = "#" + [1, 3, 5].map((j) => Math.floor(parseInt(color.slice(j, j + 2), 16) * 0.85).toString(16).padStart(2, "0")).join("");
    }
    return color;
}

function intQsAccent(form) {
    const picked = form.querySelector(".js-int-qs-accent:checked");
    if (!picked) {
        return null;
    }
    return picked.value === "custom" ? form.querySelector(".js-int-qs-custom").value : picked.value;
}

function intQsRefresh(form) {
    const preview = form.parentElement.querySelector(".js-int-qs-preview");
    if (!preview) {
        return;
    }
    const accent = intQsAccent(form);
    if (accent) {
        preview.style.setProperty("--int-accent", accent);
        preview.style.setProperty("--int-accent-text", intQsReadable(accent));
    }
    const sub = form.querySelector(".js-int-qs-sub");
    const footer = form.querySelector(".js-int-qs-footer");
    preview.querySelector(".js-int-qs-preview-sub").textContent = sub ? sub.value : "";
    preview.querySelector(".js-int-qs-preview-footer").textContent = footer ? footer.value : "";
}

document.addEventListener("input", (ev) => {
    const form = ev.target.closest(".js-int-qs-form");
    if (!form) {
        return;
    }
    if (ev.target.classList.contains("js-int-qs-custom")) {
        form.querySelector(".js-int-qs-custom-pick").checked = true;
    }
    intQsRefresh(form);
});

document.addEventListener("change", (ev) => {
    const form = ev.target.closest(".js-int-qs-form");
    if (!form) {
        return;
    }
    if (ev.target.classList.contains("js-int-qs-logo")) {
        const file = ev.target.files && ev.target.files[0];
        const img = form.parentElement.querySelector(".js-int-qs-preview-logo");
        if (file && img && /^image\/(png|jpeg|webp)$/.test(file.type)) {
            img.src = URL.createObjectURL(file);
            img.classList.remove("d-none");
        }
    }
    intQsRefresh(form);
});
