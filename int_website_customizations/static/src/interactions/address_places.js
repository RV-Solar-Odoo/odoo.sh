import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { CustomerAddress } from "@portal/interactions/address";
import { Form } from "@website/snippets/s_website_form/form";

let enabledPromise;

function placesEnabled() {
    enabledPromise ||= rpc("/website/places/config")
        .then((result) => Boolean(result && result.enabled))
        .catch(() => false);
    return enabledPromise;
}

function sessionToken() {
    if (crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return "00000000-0000-4000-8000-000000000000";
}

// Checkout, the customer account, and any website form with a street field.
async function attachPlaces(interaction, form, root) {
    const street = form?.querySelector("input[name='street']");
    if (!street) {
        return null;
    }
    if (!(await interaction.waitFor(placesEnabled()))) {
        return null;
    }
    return new Places(interaction, form, root || form, street);
}

class Places {
    constructor(interaction, form, root, street) {
        this.interaction = interaction;
        this.form = form;
        this.root = root;
        this.street = street;
        this.session = sessionToken();
        this.accepted = "";
        this.suggestSeq = 0;
        // Odoo's own autocomplete already draws a menu when this is "1".
        this.suggesting = street.dataset.autocompleteEnabled !== "1";
        this.interaction.addListener(street, "input", () => this.onType());
        if (this.suggesting) {
            street.autocomplete = "off";
            street.parentElement.classList.add("int-places-field");
            this.interaction.addListener(street, "blur", () => {
                setTimeout(() => this.closeMenu(), 200);
            });
        }
    }

    onType() {
        this.accepted = "";
        this.street.classList.remove("is-invalid");
        const host = this.root.querySelector("#errors")
            || this.street.parentElement.querySelector(".int-places-note");
        host?.replaceChildren();
        if (!this.suggesting) {
            return;
        }
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.suggest(), 300);
    }

    async suggest() {
        this.closeMenu();
        const partial = this.street.value.trim();
        if (partial.length < 3) {
            return;
        }
        const seq = ++this.suggestSeq;
        let result;
        try {
            result = await this.interaction.waitFor(rpc("/website/places/suggest", {
                partial,
                country_code: this.countryCode(),
                session_token: this.session,
            }));
        } catch {
            return;
        }
        if (seq !== this.suggestSeq || !this.street.isConnected) {
            return;
        }
        const rows = (result && result.results) || [];
        if (!rows.length) {
            return;
        }
        const menu = document.createElement("ul");
        menu.className = "int-places-menu";
        menu.setAttribute("role", "listbox");
        for (const row of rows) {
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = row.label;
            button.addEventListener("mousedown", (event) => event.preventDefault());
            button.addEventListener("click", () => this.choose(row.place_id));
            item.appendChild(button);
            menu.appendChild(item);
        }
        const credit = document.createElement("li");
        credit.className = "int-places-credit";
        credit.textContent = "Powered by Google";
        menu.appendChild(credit);
        this.street.parentElement.appendChild(menu);
        this.menu = menu;
    }

    async choose(placeId) {
        this.closeMenu();
        let result;
        try {
            result = await this.interaction.waitFor(rpc("/website/places/details", {
                place_id: placeId,
                session_token: this.session,
            }));
        } catch {
            return;
        }
        this.session = sessionToken();
        if (result && result.address) {
            await this.apply(result.address);
        }
    }

    closeMenu() {
        this.menu?.remove();
        this.menu = null;
    }

    countryCode() {
        const country = this.form.country_id || this.form.querySelector("[name='country_id']");
        return country?.selectedOptions?.[0]?.getAttribute("code") || "";
    }

    payload() {
        const form = this.form;
        const country = form.country_id || form.querySelector("[name='country_id']");
        const state = form.state_id || form.querySelector("[name='state_id']");
        const value = (name) => (form[name] || form.querySelector(`[name='${name}']`))?.value || "";
        return {
            street: value("street").trim(),
            street2: value("street2").trim(),
            city: value("city").trim(),
            zip_code: value("zip").trim(),
            country_id: country?.value || "",
            state_id: state?.value || "",
            country_code: country?.selectedOptions?.[0]?.getAttribute("code") || "",
            state_name: state?.selectedOptions?.[0]?.textContent?.trim() || "",
        };
    }

    key() {
        const values = this.payload();
        return [values.street, values.street2, values.city, values.zip_code, values.country_id, values.state_id].join("|");
    }

    hidden() {
        const street = this.street;
        if (street.disabled) {
            return true;
        }
        const parent = street.closest("#div_street") || street.parentElement;
        return parent && parent.style && parent.style.display === "none";
    }

    host() {
        return this.root.querySelector("#errors")
            || this.root.querySelector("#s_website_form_result, #o_website_form_result")
            || this.note();
    }

    note() {
        let note = this.street.parentElement.querySelector(".int-places-note");
        if (!note) {
            note = document.createElement("div");
            note.className = "int-places-note";
            this.street.parentElement.appendChild(note);
        }
        return note;
    }

    async apply(address) {
        const form = this.form;
        const field = (name) => form[name] || form.querySelector(`[name='${name}']`);
        if (address.street) {
            field("street").value = address.street;
        }
        if (address.street2 && field("street2")) {
            field("street2").value = address.street2;
        }
        if (address.city && field("city")) {
            field("city").value = address.city;
        }
        if (address.zip_code && field("zip")) {
            field("zip").value = address.zip_code;
        }
        const country = field("country_id");
        if (address.country_id && country && String(country.value) !== String(address.country_id)) {
            country.value = String(address.country_id);
            if (this.interaction.onChangeCountry) {
                await this.interaction.onChangeCountry();
            } else {
                country.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }
        const state = field("state_id");
        if (address.state_id && state?.options) {
            const value = String(address.state_id);
            if ([...state.options].some((option) => option.value === value)) {
                state.value = value;
                state.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }
    }

    show(message, address) {
        const host = this.host();
        host.replaceChildren();
        const text = document.createElement("h5");
        text.className = "text-danger";
        text.textContent = message;
        host.appendChild(text);
        if (!address) {
            return;
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-primary btn-sm";
        button.textContent = "Use this address";
        this.interaction.addListener(button, "click", async () => {
            button.disabled = true;
            await this.apply(address);
            this.accepted = this.key();
            host.replaceChildren();
            if (this.interaction.saveAddress) {
                this.interaction.saveAddress(new Event("click"));
            } else {
                this.interaction.send();
            }
        });
        host.appendChild(button);
    }

    async allowSubmit() {
        if (this.hidden() || !this.street.value.trim()) {
            return true;
        }
        if (this.accepted && this.accepted === this.key()) {
            return true;
        }
        let result;
        try {
            result = await this.interaction.waitFor(rpc("/website/places/validate", this.payload()));
        } catch {
            return this.form.isConnected;
        }
        if (!result || !result.enabled || result.status === "unavailable" || result.status === "accept") {
            if (result && result.status === "accept" && result.address) {
                await this.apply(result.address);
            }
            this.host().replaceChildren();
            this.accepted = this.key();
            return true;
        }
        this.street.classList.add("is-invalid");
        this.show(result.message, result.status === "confirm" ? result.address : null);
        return false;
    }
}

patch(CustomerAddress.prototype, {
    setup() {
        super.setup();
        this._intPlaces = null;
    },
    // Listeners can only be added once the interaction has started.
    start() {
        super.start();
        this._intPlacesReady = attachPlaces(this, this.addressForm, this.el)
            .then((places) => {
                this._intPlaces = places;
            })
            .catch(() => {
                this._intPlaces = null;
            });
    },
    async saveAddress(ev) {
        await this._intPlacesReady;
        if (this._intPlaces && !(await this._intPlaces.allowSubmit())) {
            return;
        }
        return super.saveAddress(ev);
    },
});

patch(Form.prototype, {
    setup() {
        super.setup();
        this._intPlaces = null;
    },
    start() {
        super.start();
        this._intPlacesReady = attachPlaces(this, this.el, this.el)
            .then((places) => {
                this._intPlaces = places;
            })
            .catch(() => {
                this._intPlaces = null;
            });
    },
    async send() {
        await this._intPlacesReady;
        if (this._intPlaces && !(await this._intPlaces.allowSubmit())) {
            return false;
        }
        return super.send(...arguments);
    },
});
