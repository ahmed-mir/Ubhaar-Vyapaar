(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const disclosures = document.querySelectorAll(
        ".landing-faq-list details, .public-faq-list details"
    );
    const controllers = [];

    if (!disclosures.length) return;

    const transitionTime = (element) => {
        const styles = window.getComputedStyle(element);
        const durations = styles.transitionDuration.split(",");
        const delays = styles.transitionDelay.split(",");
        const toMilliseconds = (value) => {
            const amount = Number.parseFloat(value) || 0;
            return value.trim().endsWith("ms") ? amount : amount * 1000;
        };

        return Math.max(
            0,
            ...durations.map((duration, index) =>
                toMilliseconds(duration) + toMilliseconds(delays[index % delays.length])
            )
        );
    };

    disclosures.forEach((details) => {
        const summary = Array.from(details.children).find((child) => child.tagName === "SUMMARY");
        const answer = Array.from(details.children).find((child) =>
            child.classList.contains("faq-answer-motion")
        );
        if (!summary || !answer) return;

        details.dataset.faqMotion = "ready";
        let requestedOpen = details.open;
        let sequence = 0;
        let animationFrame = 0;
        let fallbackTimer = 0;
        let pendingTransition = null;

        const clearInlineMotion = () => {
            details.removeAttribute("data-faq-animating");
            answer.style.removeProperty("height");
            answer.style.removeProperty("opacity");
            answer.style.removeProperty("transform");
        };

        const cancelPending = () => {
            sequence += 1;
            if (animationFrame) window.cancelAnimationFrame(animationFrame);
            if (fallbackTimer) window.clearTimeout(fallbackTimer);
            animationFrame = 0;
            fallbackTimer = 0;
            pendingTransition = null;
            return sequence;
        };

        const setImmediately = (open) => {
            cancelPending();
            requestedOpen = open;
            details.open = open;
            clearInlineMotion();
        };

        const finish = (open, currentSequence) => {
            if (currentSequence !== sequence) return;
            if (fallbackTimer) window.clearTimeout(fallbackTimer);
            fallbackTimer = 0;
            animationFrame = 0;
            pendingTransition = null;
            details.open = open;
            clearInlineMotion();
        };

        answer.addEventListener("transitionend", (event) => {
            if (event.target !== answer || event.propertyName !== "height" || !pendingTransition) {
                return;
            }

            const { open, currentSequence } = pendingTransition;
            const height = answer.getBoundingClientRect().height;
            const atDestination = open
                ? height >= answer.scrollHeight - 1
                : height <= 1;
            if (atDestination) finish(open, currentSequence);
        });

        const animateTo = (open) => {
            requestedOpen = open;
            const currentSequence = cancelPending();

            if (reducedMotion.matches) {
                details.open = open;
                clearInlineMotion();
                return;
            }

            const wasOpen = details.open;
            const startHeight = wasOpen ? answer.getBoundingClientRect().height : 0;
            const computedAnswer = wasOpen ? window.getComputedStyle(answer) : null;
            const startOpacity = computedAnswer ? computedAnswer.opacity : "0";
            const startTransform = computedAnswer
                ? computedAnswer.transform
                : "translateY(-2px)";

            if (open) details.open = true;
            details.setAttribute("data-faq-animating", "");
            answer.style.height = `${startHeight}px`;
            answer.style.opacity = startOpacity;
            answer.style.transform = startTransform;
            void answer.offsetHeight;

            pendingTransition = { open, currentSequence };
            const finishDelay = transitionTime(answer) + 80;
            fallbackTimer = window.setTimeout(
                () => finish(open, currentSequence),
                finishDelay
            );

            if (open) {
                animationFrame = window.requestAnimationFrame(() => {
                    if (currentSequence !== sequence || !requestedOpen) return;
                    answer.style.height = `${answer.scrollHeight}px`;
                    answer.style.opacity = "1";
                    answer.style.transform = "translateY(0)";
                });
            } else {
                answer.style.height = "0px";
                answer.style.opacity = "0";
                answer.style.transform = "translateY(-2px)";
            }
        };

        summary.addEventListener("click", (event) => {
            event.preventDefault();
            animateTo(!requestedOpen);
        });

        controllers.push(() => setImmediately(requestedOpen));
    });

    const settleForReducedMotion = (event) => {
        if (event.matches) controllers.forEach((settle) => settle());
    };

    if (reducedMotion.addEventListener) {
        reducedMotion.addEventListener("change", settleForReducedMotion);
    } else if (reducedMotion.addListener) {
        reducedMotion.addListener(settleForReducedMotion);
    }
})();
