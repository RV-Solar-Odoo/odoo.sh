import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export class ShopSearchBar extends Interaction {
    static selector = "#o_wsale_products_header";

    start() {
        this.headerEl = document.querySelector("header#top");
        if (!this.headerEl) {
            return;
        }
        // Capture also catches the page scrolling inside #wrapwrap, since scroll doesn't bubble.
        this.addListener(window, "scroll.noUpdate", this.placeBelowHeader, { capture: true, passive: true });
        this.addListener(window, "resize.noUpdate", this.placeBelowHeader);
        // The header slides or fades after the scroll has stopped. Stock calls this on
        // every frame of that, so the panel moves with it and no gap opens up.
        this.registerCleanup(
            this.services.website_menus.registerCallback(() => this.placeBelowHeader())
        );
        this.placeBelowHeader();
    }

    /** Sit under the site header while it's on screen, and at the very top once it's gone. */
    placeBelowHeader() {
        // A header that fades out stays in place until it's invisible, so rise as it fades.
        const opacity = Number(getComputedStyle(this.headerEl).opacity);
        const top = Math.max(this.headerEl.getBoundingClientRect().bottom * opacity, 0);
        this.el.style.setProperty("--o-int-shop-bar-top", `${top}px`);
    }
}

registry
    .category("public.interactions")
    .add("int_website_customizations.shop_search_bar", ShopSearchBar);
