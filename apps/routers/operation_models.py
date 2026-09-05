import uuid
from django.db import models


class RouterOperation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    router = models.ForeignKey("routers.NASDevice", on_delete=models.PROTECT, related_name="operations")
    action = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="pending", db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict)
    lease_until = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["router"], condition=models.Q(status__in=["pending", "running"]), name="one_live_router_operation")]
