import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

const NEW_LABEL = "new";

function readFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({ name: file.name, data: reader.result.split(",")[1] || "" });
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

// Upload Document and Change Label: pick a label, or type a new one.
export class LeadDocumentDialog extends Component {
    static template = "int_crm_customizations.LeadDocumentDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: String,
        labels: Array,
        labelId: { type: Number, optional: true },
        withFiles: Boolean,
        save: Function,
    };

    setup() {
        this.NEW_LABEL = NEW_LABEL;
        this.state = useState({
            label: String(this.props.labelId || this.props.labels[0]?.id || NEW_LABEL),
            newLabel: "",
            files: [],
            error: "",
            saving: false,
        });
    }

    onFiles(ev) {
        this.state.files = [...ev.target.files];
    }

    async onSave() {
        const isNew = this.state.label === NEW_LABEL;
        const newLabel = this.state.newLabel.trim();
        if (isNew && !newLabel) {
            this.state.error = _t("Type a name for the new label.");
            return;
        }
        if (this.props.withFiles && !this.state.files.length) {
            this.state.error = _t("Choose a file to upload.");
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        try {
            const files = this.props.withFiles ? await Promise.all(this.state.files.map(readFile)) : [];
            await this.props.save({
                labelId: isNew ? false : Number(this.state.label),
                newLabel: isNew ? newLabel : "",
                files,
            });
            this.props.close();
        } catch (error) {
            this.state.saving = false;
            throw error;
        }
    }
}
