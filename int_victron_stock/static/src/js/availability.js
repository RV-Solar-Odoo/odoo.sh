/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import VariantMixin from "@website_sale/js/variant_mixin";
import { ClickAndCollectAvailability } from "@website_sale_collect/js/click_and_collect_availability/click_and_collect_availability";

ClickAndCollectAvailability.props = {
    ...ClickAndCollectAvailability.props,
    availabilityLines: { type: Array, optional: true },
};

patch(ClickAndCollectAvailability.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.availabilityLines = this.props.availabilityLines || [];
    },

    _updateStateWithCombinationInfo(combinationInfo) {
        super._updateStateWithCombinationInfo(...arguments);
        if (combinationInfo.int_availability_lines) {
            this.state.availabilityLines = combinationInfo.int_availability_lines;
        }
    },

    get warehouseLine() {
        return (this.state.availabilityLines || []).find((line) => line.status === "immediate");
    },

    get supplierLine() {
        return (this.state.availabilityLines || []).find((line) => line.status === "backup");
    },

    get unavailableLine() {
        return (this.state.availabilityLines || []).find((line) => line.status === "unavailable");
    },
});

function renderAvailability(parent, combination) {
    const box = parent.querySelector(".o_int_shipping_badge");
    const lines = combination.int_availability_lines;
    if (!box || !lines) {
        return;
    }
    box.replaceChildren();
    for (const line of lines) {
        const badge = document.createElement("span");
        const icon = document.createElement("i");
        icon.className = `fa fa-fw ${line.icon}`;
        icon.setAttribute("role", "presentation");
        badge.append(icon);
        if (line.qty) {
            badge.className = `badge o_int_avail_line ${line.css}`;
            const qty = document.createElement("span");
            qty.className = "o_int_avail_qty";
            const sizer = document.createElement("span");
            sizer.className = "o_int_avail_qty_sizer";
            sizer.setAttribute("aria-hidden", "true");
            sizer.textContent = "20+";
            const value = document.createElement("span");
            value.className = "o_int_avail_qty_value";
            value.textContent = line.qty;
            qty.append(sizer, value);
            const text = document.createElement("span");
            text.className = "o_int_avail_text";
            text.textContent = line.text;
            badge.append(qty, text);
        } else {
            badge.className = `badge o_int_avail_plain ${line.css}`;
            icon.className = `fa fa-fw ${line.icon} me-1`;
            badge.append(document.createTextNode(line.label));
        }
        box.append(badge);
    }
}

const stockChange = VariantMixin._onChangeCombinationStock;
VariantMixin._onChangeCombinationStock = async function (ev, parent, combination) {
    if (stockChange) {
        await stockChange.call(this, ev, parent, combination);
    }
    renderAvailability(parent, combination);
};
