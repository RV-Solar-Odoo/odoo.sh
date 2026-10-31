import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { redirect } from "@web/core/utils/urls";

export class HideOutOfStock extends Interaction {
    static selector = ".o_int_hide_out_of_stock";
    dynamicContent = {
        _root: { "t-on-change": this.onChange },
    };

    onChange() {
        redirect(this.el.dataset.href);
    }
}

registry
    .category("public.interactions")
    .add("int_victron_stock.hide_out_of_stock", HideOutOfStock);
