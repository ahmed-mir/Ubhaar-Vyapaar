document.addEventListener(
    "error",
    (event) => {
        const image = event.target;

        if (!(image instanceof HTMLImageElement) || !image.closest("[data-listing-media]")) {
            return;
        }

        image.closest("[data-listing-media]").classList.add("media-failed");
        image.remove();
    },
    true,
);
