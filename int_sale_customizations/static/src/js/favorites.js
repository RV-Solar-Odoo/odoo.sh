// Favorite Orders: the save dialog, quantity steppers, and the edit page
// (remove a product, add one by name or SKU). Everything also works as plain
// form posts; this only fills in and tidies.

function intFavText(tag, className, text) {
    const el = document.createElement(tag);
    if (className) {
        el.className = className;
    }
    el.textContent = text;
    return el;
}

// Save to Favorite Orders: point the form at the starred order, name it by
// its order number.
document.addEventListener("show.bs.modal", (ev) => {
    if (ev.target.id !== "int_fav_modal") {
        return;
    }
    const star = ev.relatedTarget;
    const form = ev.target.querySelector(".js-int-fav-form");
    if (!star || !form || !star.dataset.intOrder) {
        return;
    }
    form.action = `/my/orders/${encodeURIComponent(star.dataset.intOrder)}/favorite`;
    form.querySelector("input[name='name']").value = star.dataset.intName || "";
});

document.addEventListener("shown.bs.modal", (ev) => {
    if (!ev.target.classList.contains("o_int_fav_modal")) {
        return;
    }
    const input = ev.target.querySelector("input[name='name']");
    if (input) {
        input.focus();
        input.select();
    }
});

// Quantity − and +.
document.addEventListener("click", (ev) => {
    const button = ev.target.closest("[data-int-step]");
    if (!button) {
        return;
    }
    const input = button.parentElement.querySelector("input[type='number']");
    if (!input) {
        return;
    }
    const min = Number(input.min || 0);
    const max = Number(input.max || 9999);
    const next = Math.min(max, Math.max(min, (Number(input.value) || 0) + Number(button.dataset.intStep)));
    input.value = String(next);
});

// Edit Favorite: the bin marks a product for removal; a second click keeps it.
document.addEventListener("click", (ev) => {
    const button = ev.target.closest(".js-int-fav-remove");
    if (!button) {
        return;
    }
    const row = button.closest("[data-int-line]");
    if (!row) {
        return;
    }
    if (row.dataset.intNew) {
        row.remove();
        return;
    }
    const input = row.querySelector(".js-int-fav-remove-input");
    const removing = input.value !== "1";
    input.value = removing ? "1" : "0";
    row.classList.toggle("o_int_fav_removed", removing);
    button.setAttribute("title", removing ? "Keep" : "Remove");
    button.querySelector("i").className = removing ? "fa fa-undo" : "fa fa-trash-o";
});

// Edit Favorite: add a product by name or SKU.
let intFavSearchTimer = null;
let intFavSearchSeq = 0;

function intFavAddRow(form, product) {
    const added = form.querySelector(".js-int-fav-added");
    const existing = added.querySelector(`[data-int-product='${product.id}']`);
    if (existing) {
        const qty = existing.querySelector("input[type='number']");
        qty.value = String(Math.min(9999, (Number(qty.value) || 0) + 1));
        return;
    }
    const row = document.createElement("div");
    row.className = "o_int_fav_line o_int_fav_new";
    row.dataset.intLine = "1";
    row.dataset.intNew = "1";
    row.dataset.intProduct = String(product.id);

    const img = document.createElement("img");
    img.className = "o_int_fav_thumb";
    img.src = product.image;
    img.alt = "";
    row.appendChild(img);

    const name = document.createElement("span");
    name.className = "o_int_fav_product";
    name.appendChild(intFavText("span", "", product.name));
    if (product.sku) {
        name.appendChild(intFavText("span", "o_int_fav_sku", `SKU ${product.sku}`));
    }
    row.appendChild(name);
    row.appendChild(intFavText("span", "o_int_fav_price", `${product.price_label} each`));

    const step = document.createElement("span");
    step.className = "o_int_step";
    const less = intFavText("button", "", "−");
    less.type = "button";
    less.dataset.intStep = "-1";
    less.setAttribute("aria-label", "Fewer");
    const qty = document.createElement("input");
    qty.type = "number";
    qty.min = "1";
    qty.max = "9999";
    qty.step = "1";
    qty.value = "1";
    qty.name = `add_${product.id}`;
    qty.setAttribute("aria-label", "Quantity");
    const more = intFavText("button", "", "+");
    more.type = "button";
    more.dataset.intStep = "1";
    more.setAttribute("aria-label", "More");
    step.append(less, qty, more);
    row.appendChild(step);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "o_int_fav_remove js-int-fav-remove";
    remove.title = "Remove";
    remove.setAttribute("aria-label", `Remove ${product.name}`);
    remove.appendChild(intFavText("i", "fa fa-trash-o", ""));
    row.appendChild(remove);

    added.appendChild(row);
}

function intFavShowResults(form, products) {
    const list = form.querySelector(".js-int-fav-results");
    list.replaceChildren();
    if (!products.length) {
        list.appendChild(intFavText("li", "o_int_fav_noresult", "No products found."));
    }
    for (const product of products) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "o_int_fav_result";
        const img = document.createElement("img");
        img.src = product.image;
        img.alt = "";
        button.appendChild(img);
        const label = document.createElement("span");
        label.appendChild(intFavText("span", "", product.name));
        if (product.sku) {
            label.appendChild(intFavText("small", "", `SKU ${product.sku}`));
        }
        button.appendChild(label);
        button.appendChild(intFavText("strong", "", product.price_label));
        button.appendChild(intFavText("span", "o_int_fav_result_add", "Add"));
        button.addEventListener("click", () => {
            intFavAddRow(form, product);
            list.classList.add("d-none");
            const search = form.querySelector(".js-int-fav-search");
            search.value = "";
            search.focus();
        });
        item.appendChild(button);
        list.appendChild(item);
    }
    list.classList.remove("d-none");
}

document.addEventListener("input", (ev) => {
    const search = ev.target.closest(".js-int-fav-search");
    if (!search) {
        return;
    }
    const form = search.closest(".js-int-fav-edit");
    const term = search.value.trim();
    clearTimeout(intFavSearchTimer);
    if (term.length < 2) {
        form.querySelector(".js-int-fav-results").classList.add("d-none");
        return;
    }
    intFavSearchTimer = setTimeout(async () => {
        const seq = ++intFavSearchSeq;
        try {
            const response = await fetch(`/my/favorites/products?q=${encodeURIComponent(term)}`, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const data = await response.json();
            if (seq === intFavSearchSeq) {
                intFavShowResults(form, data.products || []);
            }
        } catch {
            // Leave the list as it was; the person can try again.
        }
    }, 250);
});

// Enter in the product search picks nothing and must not save the form.
document.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && ev.target.closest(".js-int-fav-search")) {
        ev.preventDefault();
    }
});
