/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

export class ShippoRateX2ManyField extends X2ManyField {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    async openRecord(record) {
        if (!record.resId) {
            return;
        }
        await this.orm.call(record.resModel, "action_select", [[record.resId]]);
        await Promise.all(
            this.list.records.map((line) =>
                line.update({ selected: line.resId === record.resId })
            )
        );
        await this.props.record.update({ selected_line_id: record.resId });
    }
}

export const shippoRateX2ManyField = {
    ...x2ManyField,
    component: ShippoRateX2ManyField,
};

registry.category("fields").add("int_shippo_rate_lines", shippoRateX2ManyField);
