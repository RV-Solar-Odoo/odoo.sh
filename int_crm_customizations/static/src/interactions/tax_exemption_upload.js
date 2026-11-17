import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// The website editor has no setting for which file types an upload accepts.
export class TaxExemptionUpload extends Interaction {
    // The live form's upload is a custom field named "Exemption Certificate".
    static selector =
        "input[type='file']:is([name='x_tax_exemption_document'], [name='Exemption Certificate'], [name='Tax Exemption Certificate'])";

    start() {
        this.el.accept = ".pdf,.jpg,.jpeg,.png,.bmp";
    }
}

registry
    .category("public.interactions")
    .add("int_crm_customizations.tax_exemption_upload", TaxExemptionUpload);
