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
        const row = document.createElement("div");
        row.className = "mb-1";
        const badge = document.createElement("span");
        badge.className = `badge ${line.css}`;
        const icon = document.createElement("i");
        icon.className = `fa ${line.icon} me-1`;
        icon.setAttribute("role", "presentation");
        badge.append(icon, document.createTextNode(line.label));
        row.append(badge);
        box.append(row);
    }
}

const stockChange = VariantMixin._onChangeCombinationStock;
VariantMixin._onChangeCombinationStock = async function (ev, parent, combination) {
    if (stockChange) {
        await stockChange.call(this, ev, parent, combination);
    }
    renderAvailability(parent, combination);
};
