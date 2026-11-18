(function () {
    "use strict";

    document.querySelectorAll(".auth-form input[type='password']").forEach(function (input) {
        let shell = input.parentElement;
        if (!shell || !shell.matches(".password-input-shell")) {
            shell = document.createElement("div");
            shell.className = "password-input-shell";
            shell.dataset.passwordInputWrapper = "";
            input.parentNode.insertBefore(shell, input);
            shell.appendChild(input);
        }

        const fieldLabel = input.labels && input.labels.length
            ? input.labels[0].textContent.trim().replace(/[\s:*]+$/, "")
            : "password";
        const isConfirmation = /confirm/i.test(fieldLabel);
        const passwordNoun = isConfirmation
            ? "confirmation password"
            : fieldLabel.toLowerCase();
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "password-visibility-toggle";
        toggle.textContent = "Show";
        toggle.setAttribute("aria-label", "Show " + passwordNoun);
        toggle.setAttribute("aria-pressed", "false");
        toggle.setAttribute("aria-controls", input.id);

        shell.appendChild(toggle);
        toggle.addEventListener("click", function () {
            const showing = input.type === "password";
            input.type = showing ? "text" : "password";
            toggle.textContent = showing ? "Hide" : "Show";
            toggle.setAttribute(
                "aria-label",
                (showing ? "Hide " : "Show ") + passwordNoun
            );
            toggle.setAttribute("aria-pressed", String(showing));
        });
    });
})();
