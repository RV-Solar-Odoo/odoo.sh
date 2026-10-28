/** @odoo-module **/

import { Component } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const REFUND_PENDING = ["QUEUED", "PENDING", "SUCCESS"];

export class RefundShippoLabel extends Component {
    static template = "int_shippo_customizations.RefundShippoLabel";
    static props = ["*"];
    static components = { DropdownItem };

    setup() {
        this.dialog = useService("dialog");
        this.orm = useService("orm");
    }

    onSelected() {
        const root = this.env.model.root;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Refund Shippo Label"),
            body: _t(
                "Refund this unused label? Shippo sends the request to the carrier. Do not ship with this label after refunding it."
            ),
            confirmLabel: _t("Refund"),
            confirm: async () => {
                await this.orm.call("stock.picking", "action_refund_shippo_label", [[root.resId]]);
                await root.load();
            },
            cancel: () => {},
        });
    }
}

registry.category("cogMenu").add("int_shippo_refund_label", {
    Component: RefundShippoLabel,
    isDisplayed(env) {
        const root = env.model?.root;
        const data = root?.data;
        if (!root || root.resModel !== "stock.picking" || !data?.int_shippo_transaction_id) {
            return false;
        }
        return !REFUND_PENDING.includes(data.int_shippo_refund_status);
    },
});
