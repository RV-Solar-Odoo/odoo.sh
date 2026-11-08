import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// Homepage and "Apply Here" links are the same URL without .btn in the header,
// so they stay hidden by CSS. Only the header button becomes Help & Feedback.
const DEALER_BUTTON = [
    "html.o_int_approved_dealer header a.btn[href='/dealer-application']",
    "html.o_int_approved_dealer header a.btn[href^='/dealer-application?']",
    "html.o_int_approved_dealer nav a.btn[href='/dealer-application']",
    "html.o_int_approved_dealer nav a.btn[href^='/dealer-application?']",
].join(", ");

export class DealerHelpLink extends Interaction {
    static selector = DEALER_BUTTON;

    start() {
        this.el.classList.add("o_int_help_link");
        this.el.setAttribute("href", "/my/help");
        this.el.textContent = "Help & Feedback";
    }
}

registry
    .category("public.interactions")
    .add("int_website_customizations.dealer_help_link", DealerHelpLink);
