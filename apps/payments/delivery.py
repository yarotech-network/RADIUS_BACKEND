from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from .models import PaymentDelivery


def run_one_delivery():
    # A crash after SMTP acceptance is ambiguous. Do not automatically resend.
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
        else:
            accepted = send_mail("Your Wi-Fi voucher", f"Username: {voucher.username}\nPassword: {voucher.password}\n", settings.DEFAULT_FROM_EMAIL, [payment.customer_email], fail_silently=False)
            outcome, error = ("accepted", "") if accepted else ("failed", "email_not_accepted")
    except Exception:
        outcome, error = "unknown", "delivery_outcome_unknown"
    PaymentDelivery.objects.filter(pk=delivery.pk, status="sending").update(status=outcome, error_code=error, completed_at=timezone.now())
    return True
