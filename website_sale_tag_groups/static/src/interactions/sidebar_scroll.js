import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { getScrollingElement } from "@web/core/utils/scrolling";

const STORAGE_KEY = "website_sale_tag_groups.sidebar_scroll";
const SIDEBAR_SELECTOR = ".o_wsale_products_grid_before_rail";

/**
 * Tag and availability choices update in place, but anything that still reloads the
 * shop calls this first, so the shopper doesn't have to scroll back down.
 */
export function saveSidebarScroll() {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        sidebar: document.querySelector(SIDEBAR_SELECTOR)?.scrollTop || 0,
        page: getScrollingElement().scrollTop,
    }));
}

export class SidebarScroll extends Interaction {
    static selector = SIDEBAR_SELECTOR;
    dynamicContent = {
        '#o_wsale_price_range_option input[type="range"]': { "t-on-newRangeValue": saveSidebarScroll },
    };

    start() {
        const saved = sessionStorage.getItem(STORAGE_KEY);
        if (!saved) {
            return;
        }
        sessionStorage.removeItem(STORAGE_KEY);
        const { sidebar, page } = JSON.parse(saved);
        this.el.scrollTop = sidebar;
        getScrollingElement().scrollTop = page;
    }
}

registry
    .category("public.interactions")
    .add("website_sale_tag_groups.sidebar_scroll", SidebarScroll);
