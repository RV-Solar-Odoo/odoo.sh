/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SendSMSButton } from '@sms/components/sms_button/sms_button';
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";

patch(SendSMSButton.prototype, {

    setup() {
        super.setup();
        this.company = user.activeCompany;
        this.notificationService = useService("notification");
    },

    async onZoomSMSClicked(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const { record } = this.props;
        if (record.data.do_not_message || record.data.do_not_contact) {
            this.notificationService.add(_t("This contact has opted out of messages."), {
                title: _t("SMS not allowed"), type: "warning",
            });
            return;
        }
        await record.save();
        const number = record.data[this.props.name];
        const iframe = document.querySelector("iframe#zoom-embeddable-phone-iframe");
        if (!iframe || !number) {
            this.notificationService.add(_t("Zoom Phone is not available. Please try again after it loads."), {
                title: _t("Zoom Phone unavailable"), type: "warning",
            });
            return;
        }
        try {
            const config = await rpc("/zoom/config", {company_id: this.company.id});
            if (!config.enabled) return;
        } catch {
            return;
        }
        this.env.bus.trigger("zoom-phone-command", {
            type: "zp-input-sms", data: { number },
        });
    },
});
