(function () {
    "use strict";

    document.querySelectorAll("[data-account-menu]").forEach(function (menu) {
        const trigger = menu.querySelector("[data-account-menu-trigger]");
        const panel = menu.querySelector("[data-account-menu-panel]");
        if (!trigger || !panel) return;

        const setOpen = function (isOpen, restoreFocus) {
            trigger.setAttribute("aria-expanded", String(isOpen));
            panel.hidden = !isOpen;
            if (restoreFocus) trigger.focus();
        };

        trigger.addEventListener("click", function () {
            setOpen(trigger.getAttribute("aria-expanded") !== "true", false);
        });

        menu.addEventListener("click", function (event) {
            if (event.target.closest("a, form button")) setOpen(false, false);
        });

        document.addEventListener("pointerdown", function (event) {
            if (trigger.getAttribute("aria-expanded") === "true" && !menu.contains(event.target)) {
                setOpen(false, false);
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && trigger.getAttribute("aria-expanded") === "true") {
                setOpen(false, true);
            }
        });
    });
})();
