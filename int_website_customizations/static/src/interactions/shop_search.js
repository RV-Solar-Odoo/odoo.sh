import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { redirect } from "@web/core/utils/urls";

const isShopListing = () => Boolean(document.querySelector("#products_grid"));

function currentUrlWithoutSearch() {
    const url = new URL(window.location.href);
    url.searchParams.delete("search");
    url.searchParams.delete("noFuzzy");
    url.pathname = url.pathname.replace(/\/page\/\d+\/?$/, "");
    return `${url.pathname}${url.search}`;
}

export class ShopSearch extends Interaction {
    static selector = ".o_searchbar_form:has(input[data-search-type='products'])";
    dynamicContent = {
        ".search-query": { "t-on-input": this.debounced(this.onInput, 400) },
        // Capture runs before stock's submit handler, which then sees it was handled.
        _root: { "t-on-submit.capture": this.onSubmit },
    };

    setup() {
        this.inputEl = this.el.querySelector(".search-query");
    }

    onInput() {
        if (
            !this.inputEl.value.trim() &&
            isShopListing() &&
            new URLSearchParams(window.location.search).has("search")
        ) {
            redirect(currentUrlWithoutSearch());
        }
    }

    onSubmit(ev) {
        ev.preventDefault();
        const term = this.inputEl.value.trim();
        if (!term && isShopListing()) {
            redirect(currentUrlWithoutSearch());
            return;
        }
        // The form's action is the whole shop. Only the sort order carries over.
        const url = new URL(this.el.action);
        const order = new URLSearchParams(window.location.search).get("order");
        if (order) {
            url.searchParams.set("order", order);
        }
        if (this.el.querySelector("[name=noFuzzy]")?.value === "true") {
            url.searchParams.set("noFuzzy", "true");
        }
        if (term) {
            url.searchParams.set("search", term);
        }
        redirect(`${url.pathname}${url.search}`);
    }
}

registry
    .category("public.interactions")
    .add("int_website_customizations.shop_search", ShopSearch);
