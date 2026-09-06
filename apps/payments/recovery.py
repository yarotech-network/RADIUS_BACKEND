from django.db import transaction
from django.utils import timezone
from apps.vouchers.models import PaymentTransaction
from apps.vouchers.services import VoucherService
from .models import PaymentDelivery


def queue_credential_delivery(payment):
    """Queue the access-code email for a fulfilled payment, once.

    Runs inside the fulfilment transaction so a paid voucher can never exist without its delivery
    job. The partial unique constraint (one pending/sending delivery per payment) plus the
    "already delivered" check keep webhook replays and recovery retries from double-sending;
    resends after an accepted/unknown outcome remain a deliberate human action
    (`payment-recovery/{id}/deliver/` with the duplicate-risk acknowledgement).
    """
    if not payment.customer_email or payment.status != "success" or not payment.voucher_id:
        return None
    if payment.deliveries.exists():
        return None
    return PaymentDelivery.objects.create(payment=payment)


def fulfill_verified_voucher(payment, verified):
    if (not isinstance(verified, dict) or verified.get("status") != "success" or verified.get("reference") != payment.reference
            or verified.get("amount") != payment.amount or verified.get("currency") != "NGN"):
        raise ValueError("Payment verification mismatch.")
    # Record paid evidence before fulfillment. Failed voucher issuance must
    # remain visible as paid_unfulfilled and recoverable, not a second charge.
    PaymentTransaction.objects.filter(pk=payment.pk).update(verified_at=timezone.now())
    with transaction.atomic():
        locked = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
        if not locked.voucher_id:
            if locked.plan_id is None:
                raise ValueError("Payment plan is unavailable.")
            locked.voucher = VoucherService.generate_vouchers(tenant=locked.tenant, plan_id=locked.plan_id, quantity=1, source="customer")[0]
        locked.status = "success"
        locked.paid_at = locked.paid_at or timezone.now()
        locked.save(update_fields=["voucher", "status", "paid_at"])
        queue_credential_delivery(locked)
        return locked
