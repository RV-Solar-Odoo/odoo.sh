// My Portal → Users: once Resend Invite is clicked, show "Sending…" and block a
// second click while the page reloads. The server then shows "Invite Sent".
document.addEventListener("submit", (ev) => {
    const form = ev.target.closest(".o_int_resend_form");
    if (!form) {
        return;
    }
    if (form.dataset.intSending) {
        ev.preventDefault();
        return;
    }
    form.dataset.intSending = "1";
    const button = form.querySelector(".o_int_resend_btn");
    if (button) {
        // Disable after the submit has collected the form, so the post still goes.
        setTimeout(() => {
            button.disabled = true;
            button.textContent = "Sending…";
        });
    }
});
