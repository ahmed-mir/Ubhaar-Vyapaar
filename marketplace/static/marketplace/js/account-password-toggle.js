(function () {
    "use strict";

    document.querySelectorAll(".auth-form input[type='password']").forEach(function (input) {
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "password-visibility-toggle";
        toggle.textContent = "Show password";
        toggle.setAttribute("aria-label", "Show password");
        toggle.setAttribute("aria-pressed", "false");

        input.insertAdjacentElement("afterend", toggle);
        toggle.addEventListener("click", function () {
            const showing = input.type === "password";
            input.type = showing ? "text" : "password";
            toggle.textContent = showing ? "Hide password" : "Show password";
            toggle.setAttribute("aria-label", toggle.textContent);
            toggle.setAttribute("aria-pressed", String(showing));
        });
    });
})();
