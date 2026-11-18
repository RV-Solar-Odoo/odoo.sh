import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { FileModel } from "@web/core/file_viewer/file_model";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { LeadDocumentDialog } from "./lead_document_dialog";

const DOCUMENT_FIELDS = [
    "label_id",
    "attachment_id",
    "name",
    "mimetype",
    "checksum",
    "reviewed",
    "review_note",
    "partner_attachment_id",
];

// Documents tab on the lead: files grouped by label, opened in the same viewer
// as the chatter, with Reviewed saved as soon as it is ticked.
export class LeadDocumentsField extends Component {
    static template = "int_crm_customizations.LeadDocumentsField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.fileViewer = useFileViewer();
        this.state = useState({ documents: [], labels: [], canDelete: false, loading: true });
        onWillStart(async () => {
            this.state.canDelete =
                (await user.hasGroup("sales_team.group_sale_manager")) ||
                (await user.hasGroup("base.group_system"));
            await this.load(this.props.record.resId);
        });
        onWillUpdateProps(async (nextProps) => {
            await this.load(nextProps.record.resId);
        });
    }

    get leadId() {
        return this.props.record.resId;
    }

    get hasContact() {
        return Boolean(this.props.record.data.partner_id);
    }

    async load(leadId) {
        if (!leadId) {
            this.state.documents = [];
            this.state.loading = false;
            return;
        }
        const [documents, labels] = await Promise.all([
            this.orm.searchRead("int.lead.document", [["lead_id", "=", leadId]], DOCUMENT_FIELDS),
            this.orm.searchRead("int.lead.document.label", [], ["name"]),
        ]);
        this.state.documents = documents;
        this.state.labels = labels;
        this.state.loading = false;
    }

    async refresh() {
        await this.load(this.leadId);
        // The Tax Exemption tab's certificate status follows the documents.
        if (!(await this.props.record.isDirty())) {
            await this.props.record.load();
        }
    }

    get groups() {
        const groups = [];
        const byLabel = {};
        for (const doc of this.state.documents) {
            const [labelId, labelName] = doc.label_id;
            if (!byLabel[labelId]) {
                byLabel[labelId] = { id: labelId, name: labelName, documents: [] };
                groups.push(byLabel[labelId]);
            }
            byLabel[labelId].documents.push(doc);
        }
        return groups;
    }

    toFile(doc) {
        return Object.assign(new FileModel(), {
            id: doc.attachment_id[0],
            name: doc.name,
            mimetype: doc.mimetype,
            checksum: doc.checksum,
            type: "binary",
        });
    }

    isViewable(doc) {
        return this.toFile(doc).isViewable;
    }

    downloadUrl(doc) {
        return this.toFile(doc).downloadUrl;
    }

    onView(doc) {
        const files = this.state.documents.map((item) => this.toFile(item));
        const file = files[this.state.documents.indexOf(doc)];
        if (file.isViewable) {
            this.fileViewer.open(file, files);
        } else {
            window.location.href = file.downloadUrl;
        }
    }

    async onToggleReviewed(doc, ev) {
        await this.orm.write("int.lead.document", [doc.id], { reviewed: ev.target.checked });
        await this.refresh();
    }

    onDelete(doc) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete Document"),
            body: _t('Delete "%(file)s" from %(label)s? This also removes it from Files.', {
                file: doc.name,
                label: doc.label_id[1],
            }),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: async () => {
                await this.orm.unlink("int.lead.document", [doc.id]);
                await this.refresh();
            },
            cancel: () => {},
        });
    }

    async onCopyToContact(doc) {
        await this.orm.call("int.lead.document", "action_int_copy_to_contact", [[doc.id]]);
        this.notification.add(_t("Copied %(file)s to the contact.", { file: doc.name }), {
            type: "success",
        });
        await this.refresh();
    }

    async labelFrom({ labelId, newLabel }) {
        if (newLabel) {
            const [id] = await this.orm.create("int.lead.document.label", [{ name: newLabel }]);
            return id;
        }
        return labelId;
    }

    onUpload() {
        this.dialog.add(LeadDocumentDialog, {
            title: _t("Upload Document"),
            labels: this.state.labels,
            withFiles: true,
            save: async (values) => {
                const labelId = await this.labelFrom(values);
                await this.orm.create(
                    "int.lead.document",
                    values.files.map((file) => ({
                        lead_id: this.leadId,
                        label_id: labelId,
                        upload: file.data,
                        upload_name: file.name,
                    }))
                );
                await this.refresh();
            },
        });
    }

    onChangeLabel(doc) {
        this.dialog.add(LeadDocumentDialog, {
            title: _t("Change Label"),
            labels: this.state.labels,
            labelId: doc.label_id[0],
            withFiles: false,
            save: async (values) => {
                const labelId = await this.labelFrom(values);
                await this.orm.write("int.lead.document", [doc.id], { label_id: labelId });
                await this.refresh();
            },
        });
    }
}

export const leadDocumentsField = {
    component: LeadDocumentsField,
    supportedTypes: ["one2many"],
    relatedFields: [],
};

registry.category("fields").add("int_lead_documents", leadDocumentsField);
