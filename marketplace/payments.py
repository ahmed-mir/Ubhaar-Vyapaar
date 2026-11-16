"""Razorpay Test Mode helpers; browser input never determines charge amounts."""

import hashlib
import hmac

from django.conf import settings


def razorpay_test_mode_enabled():
    return bool(
        getattr(settings, "RAZORPAY_ENABLED", False)
        and getattr(settings, "RAZORPAY_KEY_ID", "").startswith("rzp_test_")
        and getattr(settings, "RAZORPAY_KEY_SECRET", "")
        and getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    )


def get_razorpay_client():
    import razorpay

    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def amount_to_paise(amount):
    """Convert a two-decimal INR Decimal into integer paise without floats."""
    paise = amount * 100
    if paise != paise.to_integral_value():
        raise ValueError("INR amount must have at most two decimal places.")
    return int(paise)


def signature_is_valid(secret, message, supplied_signature):
    if not secret or not supplied_signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, supplied_signature)


def checkout_signature_is_valid(order_id, payment_id, supplied_signature):
    message = f"{order_id}|{payment_id}".encode("utf-8")
    return signature_is_valid(
        settings.RAZORPAY_KEY_SECRET,
        message,
        supplied_signature,
    )


def webhook_signature_is_valid(raw_body, supplied_signature):
    return signature_is_valid(
        settings.RAZORPAY_WEBHOOK_SECRET,
        raw_body,
        supplied_signature,
    )
