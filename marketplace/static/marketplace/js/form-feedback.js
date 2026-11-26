(function () {
    "use strict";

    const summaries = document.querySelectorAll("[data-form-error-summary]");
    summaries.forEach(function (summary) {
        summary.focus();
    });

    document.addEventListener("click", function (event) {
        const dismissCookieConfirmation = event.target.closest("[data-dismiss-cookie-preference]");
        if (dismissCookieConfirmation) {
            const cookieConfirmation = dismissCookieConfirmation.closest("#cookie-preference-status");
            if (cookieConfirmation) cookieConfirmation.hidden = true;
            return;
        }

        const dismissButton = event.target.closest("[data-dismiss-message]");
        if (!dismissButton) return;

        const message = dismissButton.closest(".message");
        const messageList = message && message.parentElement;
        if (!message || !messageList) return;

        const siblings = Array.from(messageList.querySelectorAll(".message"));
        const index = siblings.indexOf(message);
        const nextButton = siblings[index + 1]?.querySelector("[data-dismiss-message]");
        const previousButton = siblings[index - 1]?.querySelector("[data-dismiss-message]");
        message.remove();

        if (document.activeElement === document.body) {
            (nextButton || previousButton || document.querySelector("#main-content"))?.focus();
        }
    });
})();
