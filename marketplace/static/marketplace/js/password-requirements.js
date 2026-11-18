(function () {
    "use strict";

    function characters(value) {
        return Array.from(value);
    }

    function isEntirelyNumeric(value) {
        return value.length > 0 && /^[\p{N}]+$/u.test(value);
    }

    function hasSymbol(value) {
        return characters(value).some(function (character) {
            return !/[\p{L}\p{N}]/u.test(character);
        });
    }

    function quickRatio(first, second) {
        const firstChars = characters(first);
        const secondChars = characters(second);
        if (!firstChars.length && !secondChars.length) return 1;

        const available = new Map();
        secondChars.forEach(function (character) {
            available.set(character, (available.get(character) || 0) + 1);
        });

        let matches = 0;
        firstChars.forEach(function (character) {
            const count = available.get(character) || 0;
            if (count > 0) {
                matches += 1;
                available.set(character, count - 1);
            }
        });

        return (2 * matches) / (firstChars.length + secondChars.length);
    }

    function similarToAttribute(password, rawValue, maxSimilarity) {
        const value = (rawValue || "").toLowerCase();
        const candidate = password.toLowerCase();
        if (!value || !candidate) return false;

        const parts = value.split(/[^\p{L}\p{N}_]+/u).concat(value);
        return parts.some(function (part) {
            if (!part) return false;
            const passwordLength = characters(candidate).length;
            const valueLength = characters(part).length;
            const lengthRatioTooSmall = passwordLength >= 10 * valueLength &&
                valueLength < (maxSimilarity / 2) * passwordLength;
            if (lengthRatioTooSmall) return false;
            return quickRatio(candidate, part) >= maxSimilarity;
        });
    }

    document.querySelectorAll("[data-password-requirements]").forEach(function (panel) {
        const form = panel.closest("form");
        const password = form && form.querySelector('[name="password1"]');
        const confirmation = form && form.querySelector('[name="password2"]');
        const username = form && form.querySelector('[name="username"]');
        const email = form && form.querySelector('[name="email"]');
        const liveStatus = panel.querySelector("[data-password-live-status]");
        const rules = Array.from(panel.querySelectorAll('[data-live-check="true"]'));

        if (!form || !password) return;

        let announceTimer = null;
        let lastAnnouncement = "";

        function setRuleState(rule, state) {
            const indicator = rule.querySelector("[data-password-indicator]");
            const statusText = rule.querySelector("[data-password-status-text]");
            rule.dataset.state = state;
            if (indicator) {
                indicator.textContent = state === "met"
                    ? "\u2713"
                    : state === "error" ? "\u2715" : "\u25cb";
            }
            if (statusText) {
                statusText.textContent = state === "met"
                    ? "Meets requirement"
                    : state === "error" ? "Does not meet requirement" : "Not yet checked";
            }
        }

        function updateSimilarity(rule, value) {
            const attributes = (rule.dataset.similarityAttributes || "")
                .split(",")
                .filter(Boolean);
            const maxSimilarity = Number(rule.dataset.maxSimilarity || 0.7);
            if (!value || !attributes.length) return "pending";

            const values = attributes.map(function (name) {
                const field = form.querySelector('[name="' + name + '"]');
                return field ? field.value : "";
            });
            if (values.some(function (attribute) { return !attribute.trim(); })) {
                return "pending";
            }

            return values.some(function (attribute) {
                return similarToAttribute(value, attribute, maxSimilarity);
            }) ? "error" : "met";
        }

        function updateRules() {
            const value = password.value;
            let metCount = 0;
            let pendingCount = 0;

            rules.forEach(function (rule) {
                const kind = rule.dataset.passwordRule;
                let state = "pending";

                if (value) {
                    if (kind === "minimum_length") {
                        state = characters(value).length >= Number(rule.dataset.minimumLength || 0)
                            ? "met" : "pending";
                    } else if (kind === "symbol") {
                        state = hasSymbol(value) ? "met" : "pending";
                    } else if (kind === "not_numeric") {
                        state = isEntirelyNumeric(value) ? "pending" : "met";
                    } else if (kind === "similarity") {
                        state = updateSimilarity(rule, value);
                    }
                }

                setRuleState(rule, state);
                if (state === "met") metCount += 1;
                if (state === "pending") pendingCount += 1;
            });

            if (liveStatus && value) {
                const pending = pendingCount
                    ? " Some checks are still waiting for input."
                    : "";
                scheduleAnnouncement(
                    metCount + " of " + rules.length + " live password requirements met." + pending +
                    " Django performs the final check when you submit."
                );
            } else if (liveStatus) {
                scheduleAnnouncement("Password requirements will update as you type.");
            }
        }

        function scheduleAnnouncement(message) {
            if (!liveStatus || message === lastAnnouncement) return;
            window.clearTimeout(announceTimer);
            announceTimer = window.setTimeout(function () {
                if (message !== lastAnnouncement) {
                    liveStatus.textContent = message;
                    lastAnnouncement = message;
                }
            }, 350);
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

        [password, username, email].filter(Boolean).forEach(function (field) {
            field.addEventListener("input", updateRules);
        });
        password.addEventListener("input", updateConfirmation);
        if (confirmation) confirmation.addEventListener("input", updateConfirmation);

        updateRules();
        updateConfirmation();
    });
})();
