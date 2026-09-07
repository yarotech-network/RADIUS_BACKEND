"""Email verification via one-time passwords (OTP).

A newly registered tenant owner receives a 6-digit code at their email address
and must confirm it before they can sign in. Only the HMAC-SHA256 hash of the
code is stored. Issuing a new code invalidates any outstanding one for the same
user, codes expire after 10 minutes and tolerate at most 5 wrong attempts.

Delivery mirrors the voucher-credential pipeline (apps.payments.delivery):
Resend's HTTPS API when ``RESEND_API_KEY`` is configured, Django's email
backend (console in development) otherwise.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailVerificationCode

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _hash_code(code):
    """HMAC-SHA256 of the code keyed with SECRET_KEY (fixed-length hex digest)."""
    return hmac.new(
        settings.SECRET_KEY.encode(), f"email-verification:{code}".encode(), hashlib.sha256
    ).hexdigest()


def _generate_code():
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def outstanding_code(user):
    """The newest code for this user, or None. May already be expired/consumed."""
    return user.email_codes.order_by("-created_at").first()


def issue_code(user):
    """Invalidate outstanding codes and create a fresh one. Returns the plain code."""
    EmailVerificationCode.objects.filter(user=user, consumed_at__isnull=True).update(
        consumed_at=timezone.now()
    )
    record = EmailVerificationCode.objects.create(
        user=user,
        code_hash=_hash_code(code := _generate_code()),
        expires_at=timezone.now() + CODE_TTL,
    )
    return record, code


def check_code(user, code):
    """Validate a submitted code. Returns ``(ok, error)``; ``error`` is a
    user-facing message or None on success. Wrong codes burn an attempt."""
    record = outstanding_code(user)
    if record is None or record.consumed_at is not None:
        return False, "No active code — request a new one."
    if timezone.now() > record.expires_at:
        return False, "This code has expired — request a new one."
    if record.attempts >= MAX_ATTEMPTS:
        return False, "Too many wrong attempts — request a new code."
    if not secrets.compare_digest(record.code_hash, _hash_code(code)):
        record.attempts += 1
        record.save(update_fields=["attempts"])
        remaining = MAX_ATTEMPTS - record.attempts
        if remaining <= 0:
            return False, "Too many wrong attempts — request a new code."
        return False, f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} left."
    return True, None


def mark_verified(user, record=None):
    """Consume the code (if any) and stamp the user's email as verified."""
    if record is None:
        record = outstanding_code(user)
    if record is not None and record.consumed_at is None:
        record.consumed_at = timezone.now()
        record.save(update_fields=["consumed_at"])
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])


def build_verification_email(user, code):
    expiry_minutes = int(CODE_TTL.total_seconds() // 60)
    subject = "Your Yarotech RADIUS verification code"
    text = (
        f"Hi {user.username},\n"
        f"\n"
        f"Your verification code is: {code}\n"
        f"\n"
        f"Enter it in the app to finish creating your workspace. "
        f"The code expires in {expiry_minutes} minutes.\n"
        f"\n"
        f"If you did not create a Yarotech RADIUS account, you can ignore this email.\n"
    )
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;color:#0f172a">'
        "<h2 style=\"margin:0 0 12px;font-size:18px\">Confirm your email address</h2>"
        '<p style="margin:0 0 8px;color:#475569">Enter this code to finish creating your Yarotech RADIUS workspace:</p>'
        f'<p style="margin:0 0 20px;font-family:Consolas,Menlo,monospace;font-size:28px;letter-spacing:4px;font-weight:bold">{code}</p>'
        f'<p style="font-size:13px;color:#475569">The code expires in {expiry_minutes} minutes. '
        "If you did not create a Yarotech RADIUS account, you can ignore this email.</p>"
        "</div>"
    )
    return subject, text, html


def send_verification_email(user, code):
    """Best-effort delivery: Resend when configured, Django email backend otherwise.

    Returns True when the provider accepted the message; never raises — a
    delivery hiccup must not fail the request (the user can simply resend).
    """
    subject, text, html = build_verification_email(user, code)
    try:
        if settings.RESEND_API_KEY:
            response = requests.post(
                RESEND_ENDPOINT,
                json={
                    "from": settings.DEFAULT_FROM_EMAIL,
                    "to": [user.email],
                    "subject": subject,
                    "text": text,
                    "html": html,
                    "tags": [{"name": "kind", "value": "email_verification"}],
                },
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=settings.EMAIL_TIMEOUT,
            )
            accepted = (
                response.status_code in (200, 201) and bool(response.json().get("id"))
            )
            if not accepted:
                logger.error(
                    "Verification email rejected by Resend (%s) for user %s",
                    response.status_code,
                    user.pk,
                )
            return accepted
        send_mail(
            subject,
            text,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
            html_message=html,
        )
        return True
    except Exception:
        logger.exception("Verification email delivery failed for user %s", user.pk)
        return False
