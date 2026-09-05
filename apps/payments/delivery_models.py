import uuid
from django.db import models


class PaymentDelivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey("vouchers.PaymentTransaction", on_delete=models.PROTECT, related_name="deliveries")
    status = models.CharField(max_length=20, default="pending", db_index=True)
    error_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["payment"], condition=models.Q(status__in=["pending", "sending"]), name="one_live_payment_delivery")]
