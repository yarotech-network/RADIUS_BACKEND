import uuid
from django.conf import settings
from django.db import models


class ApiCommand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=255)
    key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default="processing")
    response = models.JSONField(null=True)
    status_code = models.PositiveSmallIntegerField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope", "key"], name="unique_api_command_key")]


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, null=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    resource = models.CharField(max_length=200)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class LegacyImportRun(models.Model):
    source_digest = models.CharField(max_length=64, unique=True)
    plan_digest = models.CharField(max_length=64)
    completed_at = models.DateTimeField(null=True)
    summary = models.JSONField(default=dict)


class LegacyRecord(models.Model):
    run = models.ForeignKey(LegacyImportRun, on_delete=models.PROTECT, related_name='records')
    source_key = models.CharField(max_length=200)
    source_digest = models.CharField(max_length=64)
    payload_encrypted = models.TextField(editable=False)
    targets = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run', 'source_key'], name='legacy_import_source_unique')]
