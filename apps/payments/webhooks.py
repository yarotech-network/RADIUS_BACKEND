import hashlib
import hmac
import json

from django.db import transaction
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.agents.models import AgentWalletFundingPayment
from apps.agents.services import AgentService
from apps.vouchers.models import PaymentTransaction
from apps.vouchers.services import VoucherService
from apps.subscriptions.models import SubscriptionPayment
from apps.subscriptions.services import SubscriptionService
from .models import PaystackWebhookEvent
from .services import get_paystack_secret, get_paystack_service
from .recovery import fulfill_verified_voucher


def _resolve_payment(reference):
    voucher_payment = PaymentTransaction.objects.select_related(
        "tenant__settings", "plan"
    ).filter(reference=reference).first()
    wallet_payment = AgentWalletFundingPayment.objects.select_related(
        "wallet__agent__tenant__settings"
    ).filter(reference=reference).first()
    subscription_payment = SubscriptionPayment.objects.select_related(
        "tenant", "plan"
    ).filter(reference=reference).first()
    matches = [
        ("voucher", voucher_payment),
        ("wallet", wallet_payment),
        ("subscription", subscription_payment),
    ]
    matches = [(kind, payment) for kind, payment in matches if payment is not None]
    if len(matches) != 1:
        return None, None
    return matches[0]


def _tenant_for(kind, payment):
    if kind == "voucher":
        return payment.tenant
    if kind == "subscription":
        # Platform subscription charges use the platform Paystack account.
        return None
    return payment.wallet.agent.tenant


def _valid_signature(raw_body, signature, secret):
    if not signature or not secret:
        return False
    computed = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(signature, computed)


@csrf_exempt
@require_POST
def paystack_webhook(request, token):
    """Authenticate, verify, deduplicate, and fulfill a Paystack event."""
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return JsonResponse({"error": "Invalid event structure"}, status=400)
    event = payload.get("event")
    data = payload.get("data") or {}
    event_id = data.get("id")
    reference = data.get("reference")
    if not event_id or not isinstance(reference, str) or not reference or len(reference) > 100:
        return JsonResponse({"error": "Missing event identity"}, status=400)

    kind, payment = _resolve_payment(reference)
    if payment is None:
        return JsonResponse({"status": "ignored"}, status=200)

    tenant = _tenant_for(kind, payment)
    signature = request.headers.get("x-paystack-signature", "")
    if not _valid_signature(request.body, signature, get_paystack_secret(tenant)):
        return JsonResponse({"error": "Invalid signature"}, status=400)
    if event != "charge.success":
        return JsonResponse({"status": "ignored"}, status=200)

    try:
        verified = get_paystack_service(tenant).verify_transaction(reference)["data"]
    except Exception:
        return JsonResponse({"error": "Payment verification unavailable"}, status=503)

    if (
        not isinstance(verified, dict)
        or verified.get("status") != "success"
        or verified.get("reference") != reference
        or verified.get("amount") != payment.amount
        or verified.get("currency") != "NGN"
    ):
        return JsonResponse({"error": "Payment verification mismatch"}, status=400)

    if kind == "voucher":
        PaymentTransaction.objects.filter(pk=payment.pk).update(verified_at=timezone.now())

    try:
        with transaction.atomic():
            webhook_event, created = PaystackWebhookEvent.objects.get_or_create(
                event_id=str(event_id),
                defaults={"event_type": event, "payload": payload},
            )
            if not created and webhook_event.processed:
                return JsonResponse({"status": "duplicate"}, status=200)

            if kind == "voucher":
                locked = fulfill_verified_voucher(payment, verified)
                locked.paystack_reference = str(event_id)
                locked.save(update_fields=["paystack_reference"])
            elif kind == "wallet":
                AgentService.complete_wallet_funding(payment)
            else:
                SubscriptionService.complete_payment(payment)

            webhook_event.processed = True
            webhook_event.save(update_fields=["processed"])
    except Exception:
        return JsonResponse({"error": "Payment fulfillment failed"}, status=503)

    return JsonResponse({"status": "ok"}, status=200)
