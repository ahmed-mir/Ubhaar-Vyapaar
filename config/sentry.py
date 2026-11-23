"""Optional, privacy-conscious Sentry initialization."""

import logging


def initialize_sentry(
    *,
    dsn,
    environment,
    release,
    traces_sample_rate,
    before_send,
    traces_sampler,
):
    """Initialize the Django SDK only when an operator supplied a DSN."""
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[DjangoIntegration()],
            environment=environment,
            release=release,
            send_default_pii=False,
            traces_sample_rate=traces_sample_rate,
            traces_sampler=traces_sampler,
            before_send=before_send,
            include_local_variables=False,
        )
    except Exception as exc:
        logging.getLogger("django").warning(
            "Optional Sentry initialization failed (%s).",
            type(exc).__name__,
        )
        return False
    return True
