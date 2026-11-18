(function () {
    "use strict";

    function characterCount(value) {
        return Array.from(value).length;
    }

    function isEntirelyNumeric(value) {
        return value.length > 0 && /^[\p{N}]+$/u.test(value);
    }

    document.querySelectorAll("[data-password-requirements]").forEach(function (panel) {
        const form = panel.closest("form");
        const field = panel.closest(".form-field");
        const password = form && form.querySelector('[name="password1"]');
        const confirmation = form && form.querySelector('[name="password2"]');
        const liveStatus = panel.querySelector("[data-password-live-status]");

        if (!form || !field || !password) return;

        const rules = Array.from(panel.querySelectorAll("[data-password-rule]"));
        const liveRules = rules.filter(function (rule) {
            return rule.dataset.liveCheck === "true";
        });

        function setRuleState(rule, passed) {
            const indicator = rule.querySelector("[data-password-indicator]");
            const statusText = rule.querySelector("[data-password-status-text]");
            rule.dataset.state = passed ? "met" : "pending";
            if (indicator) indicator.textContent = passed ? "\u2713" : "\u25cb";
            if (statusText) statusText.textContent = passed ? "Met" : "Not yet met";
        }

        function updateRules() {
            const value = password.value;
            let passedCount = 0;

            liveRules.forEach(function (rule) {
                const kind = rule.dataset.passwordRule;
                let passed = false;

                if (value) {
                    if (kind === "minimum_length") {
                        passed = characterCount(value) >= Number(rule.dataset.minimumLength || 0);
                    } else if (kind === "not_numeric") {
                        passed = !isEntirelyNumeric(value);
                    }
                }

                setRuleState(rule, passed);
                if (passed) passedCount += 1;
            });

            if (liveStatus) {
                if (!value) {
                    liveStatus.textContent = "Enter a password to check the live requirements.";
                } else if (!liveRules.length) {
                    liveStatus.textContent = "Live checks are unavailable; Django checks the password when you submit.";
                } else {
                    liveStatus.textContent = passedCount + " of " + liveRules.length +
                        " live password requirements met. Other requirements are checked when you submit.";
                }
            }
        }

        function updateConfirmation() {
            const status = form.querySelector("[data-password-match]");
            if (!status || !confirmation) return;

            const message = status.querySelector("[data-password-match-message]");
            const indicator = status.querySelector("[data-password-match-indicator]");
            const spokenStatus = status.querySelector("[data-password-match-status]");

            if (!password.value || !confirmation.value) {
                status.dataset.state = "pending";
                if (indicator) indicator.textContent = "\u25cb";
                if (message) message.textContent = "Enter both passwords to check that they match.";
                if (spokenStatus) spokenStatus.textContent = "Enter both passwords to check that they match.";
                return;
            }

            const matches = password.value === confirmation.value;
            status.dataset.state = matches ? "met" : "error";
            if (indicator) indicator.textContent = matches ? "\u2713" : "\u2715";
            if (message) message.textContent = matches ? "Passwords match" : "Passwords do not match";
            if (spokenStatus) spokenStatus.textContent = matches ? "Passwords match." : "Passwords do not match.";
        }

        password.addEventListener("focus", function () {
            panel.open = true;
            updateRules();
            updateConfirmation();
        });
        password.addEventListener("input", function () {
            updateRules();
            updateConfirmation();
        });

        if (confirmation) confirmation.addEventListener("input", updateConfirmation);

        updateRules();
        updateConfirmation();
    });
})();
