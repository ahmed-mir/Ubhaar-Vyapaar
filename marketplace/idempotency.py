"""Signed workflow action tokens for replay-safe order and RFQ creation."""

import hashlib
import secrets

from django.core import signing


BUY_NOW_ACTION = "buy_now"
REQUEST_QUOTE_ACTION = "request_quote"

_ACTION_SALTS = {
    BUY_NOW_ACTION: "marketplace.workflow.buy-now.v1",
    REQUEST_QUOTE_ACTION: "marketplace.workflow.request-quote.v1",
}


def issue_workflow_action_token(*, user, listing, action):
    """Issue an unguessable token bound to one user, action, and listing."""
    salt = _ACTION_SALTS[action]
    return signing.dumps(
        {
            "user_id": user.pk,
            "listing_id": listing.pk,
            "action": action,
            "nonce": secrets.token_urlsafe(32),
        },
        salt=salt,
    )


def workflow_action_digest(token, *, user, listing, action):
    """Validate token scope and return its stable digest, or ``None``."""
    if not token or len(token) > 2048 or action not in _ACTION_SALTS:
        return None

    try:
        payload = signing.loads(token, salt=_ACTION_SALTS[action])
    except (signing.BadSignature, TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    if (
        payload.get("user_id") != user.pk
        or payload.get("listing_id") != listing.pk
        or payload.get("action") != action
        or not payload.get("nonce")
    ):
        return None

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
