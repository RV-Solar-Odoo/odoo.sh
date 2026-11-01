import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { redirect } from "@web/core/utils/urls";

export class ShipFilter extends Interaction {
    static selector = ".o_int_ship_filter";
    dynamicContent = {
        _root: { "t-on-change": this.onChange },
    };

    onChange() {
        redirect(this.el.dataset.href);
    }
}

registry
    .category("public.interactions")
    .add("int_victron_stock.ship_filter", ShipFilter);
