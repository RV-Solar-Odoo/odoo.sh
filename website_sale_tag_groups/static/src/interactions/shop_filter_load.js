import { redirect } from "@web/core/utils/urls";
import { saveSidebarScroll } from "@website_sale_tag_groups/interactions/sidebar_scroll";

// What a filter choice can change. The mobile panel's own element stays, so it stays open.
const REGIONS = [
    ".o_wsale_products_grid_before_rail",
    "#products_grid",
    "#o_wsale_offcanvas > .offcanvas-body.overflow-visible",
    "#o_wsale_offcanvas_content",
    "#o_wsale_offcanvas > .offcanvas-body.border-top",
];

let pending = null;

function reloadInstead(url) {
    saveSidebarScroll();
    redirect(url);
}

/** Sections the shopper opened or closed stay that way. */
function keepSectionState(current, next) {
    for (const section of next.querySelectorAll(".accordion-collapse[id]")) {
        const previous = current.querySelector(`[id="${section.id}"]`);
        if (!previous) {
            continue;
        }
        const isOpen = previous.classList.contains("show");
        section.classList.toggle("show", isOpen);
        const button = next.querySelector(`[data-bs-target="#${section.id}"]`);
        button?.classList.toggle("collapsed", !isOpen);
        button?.setAttribute("aria-expanded", isOpen);
    }
}

/**
 * Fetch a shop URL and swap in its results and filters without reloading the page.
 * Any failure falls back to a normal page load, so a filter always applies.
 *
 * @param {string} url
 * @param {HTMLElement} root the shop element, told when its content changed
 * @param {Object} interactions the public.interactions service
 * @param {Object} [options]
 * @param {boolean} [options.push] add a browser history entry
 */
export async function loadShopResults(url, root, interactions, { push = true } = {}) {
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    document.querySelector(".o_wsale_products_grid_table_wrapper")?.classList.add("opacity-50");

    let doc, finalUrl;
    try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) {
            throw new Error(`Shop returned ${response.status}`);
        }
        finalUrl = response.url;
        doc = new DOMParser().parseFromString(await response.text(), "text/html");
    } catch {
        if (!controller.signal.aborted) {
            reloadInstead(url);
        }
        return;
    }
    if (controller.signal.aborted) {
        return;
    }

    const pairs = REGIONS.map((selector) => [document.querySelector(selector), doc.querySelector(selector)]);
    if (!doc.querySelector("#products_grid") || pairs.some(([current, next]) => !current !== !next)) {
        reloadInstead(url);
        return;
    }

    const focused = document.activeElement;
    const focusedRegion = pairs.find(([current]) => current?.contains(focused))?.[0];
    const focusedId = focused?.id;
    try {
        for (const [current, next] of pairs) {
            if (!current) {
                continue;
            }
            interactions.stopInteractions(current);
            keepSectionState(current, next);
            current.replaceChildren(...next.childNodes);
            interactions.startInteractions(current);
        }
    } catch {
        reloadInstead(url);
        return;
    }
    if (focusedRegion && focusedId) {
        focusedRegion.querySelector(`[id="${focusedId}"]`)?.focus({ preventScroll: true });
    }
    document.title = doc.title;
    if (push) {
        history.pushState({}, "", finalUrl);
    }
    root.dispatchEvent(new CustomEvent("wsale_results_updated"));
}
