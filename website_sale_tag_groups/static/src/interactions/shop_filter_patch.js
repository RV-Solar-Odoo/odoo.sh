import { patch } from "@web/core/utils/patch";
import { WebsiteSale } from "@website_sale/interactions/website_sale";
import { Tracking } from "@website_sale/interactions/tracking";
import { loadShopResults } from "@website_sale_tag_groups/interactions/shop_filter_load";

const shopUrl = () => location.pathname + location.search;

// These stay running across a swap, so they have to pick up the new products and filters.
for (const Shop of [WebsiteSale, Tracking]) {
    patch(Shop.prototype, {
        start() {
            super.start();
            this.addListener(this.el, "wsale_results_updated", () => this.updateContent());
        },
    });
}

patch(WebsiteSale.prototype, {
    start() {
        super.start();
        if (!this.el.querySelector("#products_grid")) {
            return;
        }
        this.tagGroupsShownUrl = shopUrl();
        this.addListener(this.el, "wsale_results_updated", () => {
            this.tagGroupsShownUrl = shopUrl();
            this.tagGroupsResultsChanged = true;
        });
        // A filter on another module (Availability) asks for the same treatment.
        this.addListener(this.el, "wsale_filter_load", (ev) => {
            ev.preventDefault();
            this.tagGroupsLoad(ev.detail.url);
        });
        // Show the new results from the top when the mobile panel closes.
        this.addListener(this.el, "hidden.bs.offcanvas", () => {
            if (this.tagGroupsResultsChanged) {
                this.tagGroupsResultsChanged = false;
                this.el.querySelector("#products_grid").scrollIntoView();
            }
        });
        this.addListener(window, "popstate", () => {
            if (shopUrl() !== this.tagGroupsShownUrl) {
                this.tagGroupsLoad(shopUrl(), { push: false });
            }
        });
    },

    tagGroupsLoad(url, options) {
        loadShopResults(url, this.el, this.services["public.interactions"], options);
    },

    /**
     * Same URL as stock, loaded in place.
     *
     * @override
     */
    onChangeAttribute(ev) {
        if (!this.el.querySelector("#products_grid")) {
            return super.onChangeAttribute(ev);
        }
        const form = ev.currentTarget.closest("form");
        const attributeValues = new Map();
        const tags = new Set();
        for (const filter of form.querySelectorAll("input:checked, select")) {
            if (!filter.value) {
                continue;
            }
            if (filter.name === "attribute_value") {
                const [attributeId, attributeValueId] = filter.value.split("-");
                const valueIds = attributeValues.get(attributeId) ?? new Set();
                valueIds.add(attributeValueId);
                attributeValues.set(attributeId, valueIds);
            } else if (filter.name === "tags") {
                tags.add(filter.value);
            }
        }
        const url = new URL(form.action);
        for (const [attributeId, valueIds] of attributeValues) {
            url.searchParams.append("attribute_values", `${attributeId}-${[...valueIds].join(",")}`);
        }
        if (tags.size) {
            url.searchParams.set("tags", [...tags].join(","));
        }
        this.tagGroupsLoad(`${url.pathname}?${url.searchParams.toString()}`);
    },
});
