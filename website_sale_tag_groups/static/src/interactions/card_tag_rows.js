import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

/**
 * CSS can't tell which cards share a row, because the column count changes with the
 * screen width. Mark the cards of each row where no card has tags.
 */
export class CardTagRows extends Interaction {
    static selector = ".o_wsale_products_grid_table";

    start() {
        this.markRows();
        // The grid resizes when the columns change and when images finish loading.
        const observer = new ResizeObserver(this.debounced(this.markRows, 150));
        observer.observe(this.el);
        this.registerCleanup(() => observer.disconnect());
    }

    markRows() {
        const rows = new Map();
        for (const card of this.el.querySelectorAll(".oe_product")) {
            rows.set(card.offsetTop, [...(rows.get(card.offsetTop) || []), card]);
        }
        for (const cards of rows.values()) {
            const noTags = cards.every((card) => !card.querySelector(".o_tag_group_row"));
            for (const card of cards) {
                card.classList.toggle("rvsb-row-notags", noTags);
            }
        }
    }
}

registry
    .category("public.interactions")
    .add("website_sale_tag_groups.card_tag_rows", CardTagRows);
