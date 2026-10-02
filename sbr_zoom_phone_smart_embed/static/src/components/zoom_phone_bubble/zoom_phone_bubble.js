/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { getOrigin } from "@web/core/utils/urls";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { userBus } from "@web/core/user";
import { user } from "@web/core/user";

const BUBBLE_SIZE = 56;
const PANEL_WIDTH = 350;
const PANEL_HEIGHT = 680;

export class ZoomPhoneBubble extends Component {
    setup() {
        this.company = user.activeCompany;
        this.originDomain = getOrigin();
        this.notificationService = useService("notification");
        this.iframeRef = useRef("zoom-iframe");
        this.state = useState({
            open: false,
            position: this._initialPosition(),
            isDragging: false,
            autoDial: false,
            callNotify: false,
            iframeReady: false,
            activeRecord: null,
            enabled: false,
            embedUrl: "",
            zoomOrigin: "",
        });
        this.pendingCommand = null;
        this._onMouseMove = this._onMouseMove.bind(this);
        this._onMouseUp = this._onMouseUp.bind(this);
        this._onMessage = this._onMessage.bind(this);
        this._onResize = this._onResize.bind(this);
        this._onCommand = this._onCommand.bind(this);

        this.env.bus.addEventListener("zoom-phone-command", this._onCommand);
        onWillStart(async () => {
            await this._refreshConfig();
        });
        onMounted(() => {
            document.addEventListener("mousemove", this._onMouseMove);
            document.addEventListener("mouseup", this._onMouseUp);
            window.addEventListener("message", this._onMessage);
            window.addEventListener("resize", this._onResize);
        });
        onWillUnmount(() => {
            this.env.bus.removeEventListener("zoom-phone-command", this._onCommand);
            document.removeEventListener("mousemove", this._onMouseMove);
            document.removeEventListener("mouseup", this._onMouseUp);
            window.removeEventListener("message", this._onMessage);
            window.removeEventListener("resize", this._onResize);
        });
    }

    async _refreshConfig() {
        if (this._configRequest) return this._configRequest;
        this._configRequest = rpc("/zoom/config", {company_id: this.company.id})
            .then((config) => {
                if (!config.enabled) {
                    this.state.enabled = false;
                    this.state.open = false;
                    this.state.iframeReady = false;
                    this.state.activeRecord = null;
                    this.pendingCommand = null;
                    this.state.embedUrl = "";
                    this.state.zoomOrigin = "";
                    return false;
                }
                const embedUrl = new URL(config.embed_url);
                embedUrl.searchParams.set("originDomain", this.originDomain);
                const nextEmbedUrl = embedUrl.toString();
                if (this.state.embedUrl !== nextEmbedUrl) {
                    this.state.iframeReady = false;
                    this.state.embedUrl = nextEmbedUrl;
                }
                this.state.enabled = true;
                this.state.autoDial = config.auto_dial;
                this.state.callNotify = config.call_notification;
                this.state.zoomOrigin = config.zoom_origin;
                return true;
            })
            .catch(() => {
                // Zoom is optional; a failed configuration read must not break Odoo.
                this.state.enabled = false;
                this.state.open = false;
                return false;
            })
            .finally(() => { this._configRequest = null; });
        return this._configRequest;
    }

    _initialPosition() {
        return { x: Math.max(0, window.innerWidth - 72), y: Math.max(0, window.innerHeight - 72) };
    }

    _clampPosition(position, panelVisible = this.state?.open) {
        const panelWidth = Math.min(PANEL_WIDTH, Math.max(BUBBLE_SIZE, window.innerWidth - 16));
        const panelHeight = Math.min(PANEL_HEIGHT, Math.max(BUBBLE_SIZE, window.innerHeight - 16));
        const minX = panelVisible ? Math.max(0, panelWidth - BUBBLE_SIZE) : 0;
        const minY = panelVisible ? Math.max(0, panelHeight - BUBBLE_SIZE) : 0;
        return {
            x: Math.max(minX, Math.min(window.innerWidth - BUBBLE_SIZE, position.x)),
            y: Math.max(minY, Math.min(window.innerHeight - BUBBLE_SIZE, position.y)),
        };
    }

    async toggle() {
        await this._refreshConfig();
        if (!this.state.enabled) return;
        if (!this.state.isDragging) {
            this.state.open = !this.state.open;
            if (this.state.open) {
                this.state.position = this._clampPosition(this.state.position, true);
            }
        }
    }

    close(ev) {
        ev.stopPropagation();
        this.state.open = false;
    }

    startDrag(ev) {
        ev.preventDefault();
        this._startDrag(ev);
    }

    startPanelDrag(ev) {
        if (ev.target.closest("button")) return;
        ev.preventDefault();
        this._startDrag(ev);
    }

    _startDrag(ev) {
        ev.stopPropagation();
        this.state.isDragging = false;
        this._dragOffset = { x: ev.clientX - this.state.position.x, y: ev.clientY - this.state.position.y };
        this._dragStart = { x: ev.clientX, y: ev.clientY };
        this._draggingStarted = true;
    }

    _onMouseMove(ev) {
        if (!this._draggingStarted) return;
        if (Math.abs(ev.clientX - this._dragStart.x) > 5 || Math.abs(ev.clientY - this._dragStart.y) > 5) {
            this.state.isDragging = true;
        }
        if (this.state.isDragging) {
            this.state.position = this._clampPosition({
                x: ev.clientX - this._dragOffset.x, y: ev.clientY - this._dragOffset.y,
            });
        }
    }

    _onMouseUp() {
        this._draggingStarted = false;
        setTimeout(() => { this.state.isDragging = false; }, 100);
    }

    _onResize() {
        this.state.position = this._clampPosition(this.state.position);
    }

    onIframeLoad() {
        this.state.iframeReady = true;
        this._sendPendingCommand();
    }

    async _onCommand({ detail }) {
        // Re-check the active company at the action boundary. This prevents a
        // stale systray instance from sending a command after a company switch.
        await this._refreshConfig();
        if (!this.state.enabled || !detail?.type || !detail.data) return;
        this.state.open = true;
        this.state.position = this._clampPosition(this.state.position, true);
        if (detail.record?.resModel && Number.isInteger(detail.record.resId)) {
            this.state.activeRecord = detail.record;
        }
        this.pendingCommand = {
            type: detail.type,
            data: { ...detail.data, ...(detail.type === "zp-make-call" ? { autoDial: this.state.autoDial } : {}) },
        };
        this._sendPendingCommand();
    }

    _sendPendingCommand() {
        if (!this.pendingCommand || !this.state.iframeReady || !this.iframeRef.el?.contentWindow) return;
        this.iframeRef.el.contentWindow.postMessage(this.pendingCommand, this.state.zoomOrigin);
        this.pendingCommand = null;
    }

    async _onMessage(event) {
        if (event.origin !== this.state.zoomOrigin || event.source !== this.iframeRef.el?.contentWindow) return;
        if (event.data?.type !== "zp-call-ended-event" || !event.data.data || !this.state.activeRecord) return;
        try {
            const logged = await rpc("/add/zoom/call/log", {
                res_model: this.state.activeRecord.resModel,
                res_id: this.state.activeRecord.resId,
                call: event.data.data,
            });
            if (logged && this.state.callNotify) {
                this.notificationService.add(_t("Call log successfully linked to the record."), {
                    title: _t("Call log added"), type: "success",
                });
            }
        } catch {
            if (this.state.callNotify) {
                this.notificationService.add(_t("The call ended, but its log could not be added."), {
                    title: _t("Zoom Phone"), type: "warning",
                });
            }
        } finally {
            this.state.activeRecord = null;
        }
    }
}

ZoomPhoneBubble.template = "zoom.ZoomPhoneBubble";
registry.category("systray").add("zoom_phone_bubble", { Component: ZoomPhoneBubble }, { sequence: 5 });
