import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { getScrollingElement } from "@web/core/utils/scrolling";

const STORAGE_KEY = "website_sale_tag_groups.sidebar_scroll";

/**
 * Every filter choice reloads the shop. Remember where the sidebar and the page
 * were, so the shopper can keep ticking options without scrolling back down.
 */
export class SidebarScroll extends Interaction {
    static selector = ".o_wsale_products_grid_before_rail";
    dynamicContent = {
        _root: { "t-on-change": this.onChange },
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

    onChange() {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
            sidebar: this.el.scrollTop,
            page: getScrollingElement().scrollTop,
        }));
    }
}

registry
    .category("public.interactions")
    .add("website_sale_tag_groups.sidebar_scroll", SidebarScroll);
