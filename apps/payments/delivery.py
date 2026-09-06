from datetime import timedelta
from html import escape

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from .models import PaymentDelivery

RESEND_ENDPOINT = "https://api.resend.com/emails"


def format_duration(hours):
    if hours % 24 == 0 and hours >= 24:
        days = hours // 24
        return f"{days} day{'s' if days != 1 else ''}"
    return f"{hours} hour{'s' if hours != 1 else ''}"


def format_data_limit(megabytes):
    if not megabytes:
        return "Unlimited data"
    if megabytes % 1024 == 0:
        return f"{megabytes // 1024} GB"
    return f"{megabytes} MB"


def build_credential_email(payment):
    """Subject, plain-text and HTML bodies for a fulfilled voucher purchase.

    One access code is both the hotspot username and password (see
    `Voucher.generate_credentials`), so the customer only ever handles a single value.
    """
    voucher = payment.voucher
    plan = voucher.plan
    tenant = payment.tenant
    code = voucher.username
    subject = f"Your {tenant.name} Wi-Fi access code"
    plan_line = f"{plan.name} — {format_duration(plan.duration_hours)}, {format_data_limit(plan.data_limit)}"
    support = tenant.phone or tenant.email
    support_line = f"Need help? Contact {tenant.name} on {support}." if support else f"Need help? Contact {tenant.name}."

    text = (
        f"Thanks for buying internet access from {tenant.name}.\n"
        f"\n"
        f"Your access code: {code}\n"
        f"\n"
        f"Plan: {plan_line}\n"
        f"Amount paid: {plan.get_price_display()}\n"
        f"Payment reference: {payment.reference}\n"
        f"\n"
        f"How to connect:\n"
        f"1. Join the {tenant.name} Wi-Fi network.\n"
        f"2. On the login page, enter the access code as both username and password.\n"
        f"3. Your time starts the first time you log in.\n"
        f"\n"
        f"{support_line}\n"
    )
    html = (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;color:#0f172a\">"
        f"<h2 style=\"margin:0 0 12px;font-size:18px\">Thanks for buying internet access from {escape(tenant.name)}</h2>"
        "<p style=\"margin:0 0 8px;color:#475569\">Your access code</p>"
        f"<p style=\"margin:0 0 20px;font-family:Consolas,Menlo,monospace;font-size:28px;letter-spacing:4px;font-weight:bold\">{escape(code)}</p>"
        "<table style=\"border-collapse:collapse;font-size:14px\">"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#475569\">Plan</td><td style=\"padding:4px 0\">{escape(plan_line)}</td></tr>"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#475569\">Amount paid</td><td style=\"padding:4px 0\">{escape(plan.get_price_display())}</td></tr>"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#475569\">Reference</td><td style=\"padding:4px 0;font-family:Consolas,Menlo,monospace\">{escape(payment.reference)}</td></tr>"
        "</table>"
        "<h3 style=\"margin:20px 0 8px;font-size:15px\">How to connect</h3>"
        "<ol style=\"margin:0 0 16px;padding-left:20px;font-size:14px;line-height:1.6\">"
        f"<li>Join the {escape(tenant.name)} Wi-Fi network.</li>"
        "<li>On the login page, enter the access code as both username and password.</li>"
        "<li>Your time starts the first time you log in.</li>"
        "</ol>"
        f"<p style=\"font-size:13px;color:#475569\">{escape(support_line)}</p>"
        "</div>"
    )
    return subject, text, html


def send_via_resend(payment, subject, text, html, idempotency_key):
    """Deliver through Resend's HTTPS API. Returns True when Resend accepted the message.

    The Idempotency-Key is scoped to one delivery job, so a repeated HTTP call for the same job
    cannot produce two emails on Resend's side, while a deliberate operator resend (a new
    PaymentDelivery row) still goes out.
    """
    response = requests.post(
        RESEND_ENDPOINT,
        json={
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [payment.customer_email],
            "subject": subject,
            "text": text,
            "html": html,
            "tags": [{"name": "kind", "value": "voucher_credentials"}, {"name": "tenant", "value": str(payment.tenant_id)}],
        },
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
        timeout=settings.EMAIL_TIMEOUT,
    )
    if response.status_code >= 500:
        # Provider outage: outcome genuinely unknown, matches the SMTP exception path.
        raise RuntimeError(f"resend_unavailable_{response.status_code}")
    return response.status_code in (200, 201) and bool(response.json().get("id"))


def send_credentials(payment, idempotency_key):
    """Send the access-code email; True when the provider accepted it."""
    subject, text, html = build_credential_email(payment)
    if settings.RESEND_API_KEY:
        return send_via_resend(payment, subject, text, html, idempotency_key)
    accepted = send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [payment.customer_email], fail_silently=False, html_message=html)
    return bool(accepted)


def run_one_delivery():
    # A crash after provider acceptance is ambiguous. Do not automatically resend.
    PaymentDelivery.objects.filter(status="sending", started_at__lt=timezone.now()-timedelta(minutes=5)).update(status="unknown", error_code="delivery_outcome_unknown")
    with transaction.atomic():
        delivery = PaymentDelivery.objects.select_for_update(skip_locked=True).filter(status="pending").order_by("created_at").first()
        if delivery is None:
            return False
        delivery.status = "sending"
        delivery.started_at = timezone.now()
        delivery.save(update_fields=["status", "started_at"])
    payment = delivery.payment
    try:
        voucher = payment.voucher
        if not voucher or payment.status != "success":
            outcome, error = "failed", "payment_not_fulfilled"
        elif not payment.customer_email:
            outcome, error = "failed", "no_customer_email"
        else:
            sent = send_credentials(payment, idempotency_key=f"payment-delivery/{delivery.pk}")
            outcome, error = ("accepted", "") if sent else ("failed", "email_not_accepted")
    except Exception:
        outcome, error = "unknown", "delivery_outcome_unknown"
    PaymentDelivery.objects.filter(pk=delivery.pk, status="sending").update(status=outcome, error_code=error, completed_at=timezone.now())
    return True
