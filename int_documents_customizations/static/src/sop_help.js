/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { MainMenu } from "@stock_barcode/main_menu/main_menu";
import MainComponent from "@stock_barcode/components/main";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

// Barcode is a full-screen app with no navbar, so the icon is patched into
// that screen. Sales and Inventory use the navbar.
const SOP_NAVBAR_APPS = new Set(["sale.sale_menu_root", "stock.menu_stock_root"]);

export class SopHelpMenu extends Component {
    static template = "int_documents_customizations.SopHelpMenu";
    static components = { Dropdown, DropdownItem };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.menu = this.env.services.menu || null;
        this.state = useState({ items: [] });
        this.loadRequest = 0;
        this.onAppChanged = () => this.load();
        if (this.env.bus) {
            this.env.bus.addEventListener("MENUS:APP-CHANGED", this.onAppChanged);
            onWillUnmount(() => {
                this.env.bus.removeEventListener("MENUS:APP-CHANGED", this.onAppChanged);
            });
        }
        onWillStart(() => this.load());
    }

    appXmlId() {
        return this.props.appXmlId || this.menu?.getCurrentApp()?.xmlid;
    }

    async load() {
        const request = ++this.loadRequest;
        const appXmlId = this.appXmlId();
        if (!appXmlId) {
            this.state.items = [];
            return;
        }
        try {
            const items = await this.orm.call("documents.document", "int_sop_links", [appXmlId]);
            if (request === this.loadRequest) {
                this.state.items = items;
            }
        } catch {
            if (request === this.loadRequest) {
                this.state.items = [];
            }
        }
    }

    open(item) {
        if (!item?.url) {
            return;
        }
        // Stay on this host. access_url points at the website domain, and the
        // staff session cookie is on the Odoo host they are already using.
        const url = new URL(item.url, window.location.origin);
        window.open(`${url.pathname}${url.search}${url.hash}`, "_blank", "noopener");
    }
}

registry.category("systray").add(
    "int_documents_customizations.sop_help",
    {
        Component: SopHelpMenu,
        isDisplayed(env) {
            const app = env.services.menu?.getCurrentApp?.();
            return Boolean(app && SOP_NAVBAR_APPS.has(app.xmlid));
        },
    },
    { sequence: 22 }
);

// patch() replaces the static object, so the existing components have to be kept.
patch(MainMenu, {
    components: {
        ...(MainMenu.components || {}),
        SopHelpMenu,
    },
});
patch(MainComponent, {
    components: {
        ...(MainComponent.components || {}),
        SopHelpMenu,
    },
});
