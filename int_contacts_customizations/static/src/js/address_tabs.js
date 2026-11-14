// My addresses: keep the open tab in the address bar, so a reload or the back
// button returns to the same tab.
document.addEventListener("shown.bs.tab", (ev) => {
    const tab = ev.target.closest(".o_int_addr_tabs [data-int-tab]");
    if (!tab) {
        return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab.dataset.intTab);
    window.history.replaceState(window.history.state, "", url);
});
