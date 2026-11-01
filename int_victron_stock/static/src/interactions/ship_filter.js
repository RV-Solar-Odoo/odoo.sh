import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { redirect } from "@web/core/utils/urls";

export class ShipFilter extends Interaction {
    static selector = ".o_int_ship_filter";
    dynamicContent = {
        _root: { "t-on-change": this.onChange },
    };

    onChange() {
        // Tag Groups can load this in place. Without it, the event isn't handled and the page reloads.
        const url = this.el.dataset.href;
        const load = new CustomEvent("wsale_filter_load", { bubbles: true, cancelable: true, detail: { url } });
        if (this.el.dispatchEvent(load)) {
            redirect(url);
        }
    }
}

registry
    .category("public.interactions")
    .add("int_victron_stock.ship_filter", ShipFilter);
