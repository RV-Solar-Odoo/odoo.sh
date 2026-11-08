import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// Chrome, Safari, and mobile Safari fill these after the empty value="" has
// been parsed. readonly stops that fill. It comes off on the first tap or
// key, so a password manager can still offer a password once the person
// chooses the field. Until then, a late fill is cleared.
const CLEAR_DELAYS = [0, 50, 250, 800, 1600, 3000];
const AUTOFILL_ANIMATION = "o_int_autofill_start";

export class BlankPasswordFields extends Interaction {
    static selector = "form.oe_reset_password_form";
    static selectorHas = 'input[type="password"]';
    dynamicContent = {
        'input[type="password"]': {
            "t-on-pointerdown.capture.noUpdate.withTarget": (ev, input) => this.unlock(input),
            "t-on-keydown.noUpdate.withTarget": (ev, input) => this.unlock(input),
            "t-on-focus.noUpdate.withTarget": (ev, input) => this.unlock(input),
            "t-on-animationstart.noUpdate.withTarget": this.onAutofill,
        },
    };

    setup() {
        this.unlocked = new WeakSet();
        this.clearing = new WeakSet();
    }

    start() {
        this.passwordInputs = [...this.el.querySelectorAll('input[type="password"]')];
        for (const input of this.passwordInputs) {
            input.readOnly = true;
            input.setAttribute("readonly", "readonly");
        }
        this.clearLocked();
        for (const delay of CLEAR_DELAYS) {
            this.waitForTimeout(() => this.clearLocked(), delay);
        }
    }

    onAutofill(ev, input) {
        if (ev.animationName === AUTOFILL_ANIMATION) {
            this.clearInput(input);
        }
    }

    unlock(input) {
        if (this.unlocked.has(input)) {
            return;
        }
        this.clearInput(input);
        this.unlocked.add(input);
        input.readOnly = false;
        input.removeAttribute("readonly");
    }

    clearLocked() {
        for (const input of this.passwordInputs) {
            this.clearInput(input);
        }
    }

    clearInput(input) {
        if (this.unlocked.has(input) || this.clearing.has(input)) {
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
