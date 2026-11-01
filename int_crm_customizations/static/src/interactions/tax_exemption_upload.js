import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// The website editor has no setting for which file types an upload accepts.
export class TaxExemptionUpload extends Interaction {
    static selector = "input[type='file'][name='x_tax_exemption_document']";

    setup() {
        this.el.accept = ".pdf,.jpg,.jpeg,.png";
    }
}

registry
    .category("public.interactions")
    .add("int_crm_customizations.tax_exemption_upload", TaxExemptionUpload);
