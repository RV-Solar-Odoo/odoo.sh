import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// Any logged-in user (retail or dealer) gets Help & Feedback in the header in
// place of Become a Dealer. Public visitors keep Become a Dealer. Homepage and
// "Apply Here" links are not .btn in the header, so they are left alone here;
// for dealers they are hidden by CSS.
const DEALER_BUTTON = [
    "html.o_int_logged_in header a.btn[href='/dealer-application']",
    "html.o_int_logged_in header a.btn[href^='/dealer-application?']",
    "html.o_int_logged_in nav a.btn[href='/dealer-application']",
    "html.o_int_logged_in nav a.btn[href^='/dealer-application?']",
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
