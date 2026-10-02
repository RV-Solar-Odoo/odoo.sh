/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PhoneField } from "@web/views/fields/phone/phone_field";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";

const originalOnLinkClicked = PhoneField.prototype.onLinkClicked;

patch(PhoneField.prototype, {

    setup() {
        super.setup();
        this.company = user.activeCompany;
        this.notificationService = useService("notification");
    },

    async onLinkClicked(ev) {
        const { record } = this.props;
        if (record.data.do_not_call || record.data.do_not_contact) {
            ev.preventDefault();
            this.notificationService.add(_t("This contact has opted out of calls."), {
                title: _t("Call not allowed"), type: "warning",
            });
            return;
        }
        const phoneField = ev.target.closest(".o_field_phone");
        const fieldName = phoneField?.getAttribute("name");
        const number = fieldName && record.data[fieldName];
        const iframe = document.querySelector("iframe#zoom-embeddable-phone-iframe");
        if (!iframe || !number) {
            return originalOnLinkClicked?.call(this, ev);
        }
        // Hold the browser's native navigation while the active-company check
        // completes. The original handler is called on the fallback path.
        ev.preventDefault();
        try {
            const config = await rpc("/zoom/config", {company_id: this.company.id});
            if (!config.enabled) {
                return originalOnLinkClicked?.call(this, ev);
            }
        } catch {
            return originalOnLinkClicked?.call(this, ev);
        }
        this.env.bus.trigger("zoom-phone-command", {
            type: "zp-make-call",
            data: { number },
            record: { resModel: record.resModel, resId: record.resId },
        });
    },
});
