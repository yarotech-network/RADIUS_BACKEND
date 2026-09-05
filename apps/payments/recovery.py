from django.db import transaction
from django.utils import timezone
from apps.vouchers.models import PaymentTransaction
from apps.vouchers.services import VoucherService


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
        return locked
