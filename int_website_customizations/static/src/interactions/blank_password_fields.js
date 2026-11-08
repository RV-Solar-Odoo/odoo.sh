import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// Chrome and Safari fill these after the empty value="" has been parsed.
const CLEAR_DELAYS = [0, 50, 250, 800];
const AUTOFILL_ANIMATION = "o_int_autofill_start";

export class BlankPasswordFields extends Interaction {
    static selector = "form.oe_reset_password_form";
    static selectorHas = 'input[type="password"]';

    setup() {
        this.passwordInputs = [...this.el.querySelectorAll('input[type="password"]')];
        this.touched = new WeakSet();
        this.clearing = new WeakSet();
        for (const input of this.passwordInputs) {
            this.addListener(input, "focus", () => this.touched.add(input));
            this.addListener(input, "input", () => this.touched.add(input));
            this.addListener(input, "animationstart", (ev) => this.onAutofill(ev, input));
        }
    }

    start() {
        this.clearUntouched();
        for (const delay of CLEAR_DELAYS) {
            this.waitForTimeout(() => this.clearUntouched(), delay);
        }
    }

    onAutofill(ev, input) {
        if (ev.animationName === AUTOFILL_ANIMATION) {
            this.clearInput(input);
        }
    }

    clearUntouched() {
        for (const input of this.passwordInputs) {
            this.clearInput(input);
        }
    }

    clearInput(input) {
        if (this.touched.has(input) || this.clearing.has(input)) {
            return;
        }
        // Autofill can fire animationstart again while the value is being cleared.
        this.clearing.add(input);
        input.value = "";
        input.setAttribute("value", "");
        this.clearing.delete(input);
    }
}

registry
    .category("public.interactions")
    .add("int_website_customizations.blank_password_fields", BlankPasswordFields);
