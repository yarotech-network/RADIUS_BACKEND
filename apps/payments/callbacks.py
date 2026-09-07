"""Trusted browser return destinations, independent of webhook settlement."""
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


RETURN_PATHS = {
    "voucher": "/pay/result",
    "subscription": "/settings/subscription",
    "wallet": "/agent/wallet/return",
}


def validate_callback_origin(origin, *, require_https=False):
    message = "PAYSTACK_CALLBACK_ORIGIN must be an absolute frontend origin without credentials, path, query or fragment."
    try:
        parts = urlsplit(origin)
        valid = (
            isinstance(origin, str) and bool(origin)
            and not any(character.isspace() for character in origin)
            and "\\" not in origin
            and parts.scheme in (("https",) if require_https else ("http", "https"))
            and bool(parts.hostname)
            and parts.username is None and parts.password is None
            and parts.path in ("", "/") and not parts.query and not parts.fragment
            and "?" not in origin and "#" not in origin
        )
        # Accessing port rejects malformed or out-of-range ports.
        parts.port
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        if require_https:
            message += " Production requires an explicit HTTPS origin."
        raise ImproperlyConfigured(message)
    return origin.rstrip("/")


def payment_callback_url(kind):
    return validate_callback_origin(settings.PAYSTACK_CALLBACK_ORIGIN) + RETURN_PATHS[kind]
