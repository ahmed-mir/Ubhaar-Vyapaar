(function () {
    "use strict";

    document.querySelectorAll("[data-phone-input-group] input[name='phone']").forEach(function (input) {
        function sanitizePhone() {
            const original = input.value;
            const cursor = input.selectionStart;
            const digitsBeforeCursor = cursor === null
                ? null
                : original.slice(0, cursor).replace(/[^0-9]/g, "").length;
            const sanitized = original.replace(/[^0-9]/g, "").slice(0, 10);

            if (sanitized === original) return;

            input.value = sanitized;
            if (digitsBeforeCursor !== null && document.activeElement === input) {
                const nextPosition = Math.min(digitsBeforeCursor, sanitized.length);
                input.setSelectionRange(nextPosition, nextPosition);
            }
        }

        input.addEventListener("beforeinput", function (event) {
            if (typeof event.data === "string" && /[^0-9]/.test(event.data)) {
                event.preventDefault();
            }
        });
        input.addEventListener("input", sanitizePhone);
    });
})();
