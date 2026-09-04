from django.db import models
from django.conf import settings
import uuid


class NASDevice(models.Model):
    ONBOARDING_STATES = [
        ("pending", "Pending"),
        ("reviewed", "Reviewed"),
        ("approved", "Approved"),
        ("waiting_for_vpn", "Waiting for VPN"),
        ("vpn_failed", "VPN Failed"),
        ("testing_radius", "Testing RADIUS"),
        ("radius_failed", "RADIUS Failed"),
        ("accounting_failed", "Accounting Failed"),
        ("active", "Active"),
        ("suspended", "Suspended"),
    ]

    DEPLOYMENT_STATUSES = [
        ("not_deployed", "Not Deployed"),
        ("deploying", "Deploying"),
        ("deployed", "Deployed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    nas_secret = models.CharField(max_length=255)
    wireguard_ip = models.GenericIPAddressField(blank=True, null=True)
    wireguard_public_key = models.CharField(max_length=255, blank=True)
    wireguard_port = models.PositiveIntegerField(default=51820)
    routeros_username = models.CharField(max_length=100, blank=True)
    routeros_password_encrypted = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=200, blank=True)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="routers")
    onboarding_state = models.CharField(max_length=30, choices=ONBOARDING_STATES, default="pending")
    deployment_status = models.CharField(max_length=20, choices=DEPLOYMENT_STATUSES, default="not_deployed")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "routers_nasdevice"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["wireguard_ip"],
                condition=models.Q(wireguard_ip__isnull=False),
                name="unique_router_wireguard_ip",
            ),
            models.UniqueConstraint(
                fields=["wireguard_public_key"],
                condition=~models.Q(wireguard_public_key=""),
                name="unique_router_wireguard_public_key",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.ip_address})"

    @property
    def radius_ip(self):
        """Address FreeRADIUS should see for this router."""
        return self.wireguard_ip or self.ip_address


class RouterAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    router = models.ForeignKey(NASDevice, on_delete=models.CASCADE, related_name="audit_events")
    action = models.CharField(max_length=100)
    from_state = models.CharField(max_length=30, blank=True, null=True)
    to_state = models.CharField(max_length=30, blank=True, null=True)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routers_auditevent"
        ordering = ["-created_at"]


class RouterOnboardingCheck(models.Model):
    CHECK_TYPES = [
        ("ping", "Ping"),
        ("routeros_api", "RouterOS API"),
        ("wireguard_peer", "WireGuard Peer"),
        ("radius_auth", "RADIUS Auth"),
        ("radius_acct", "RADIUS Accounting"),
        ("firewall", "Firewall Rules"),
    ]

    router = models.ForeignKey(NASDevice, on_delete=models.CASCADE, related_name="onboarding_checks")
    check_type = models.CharField(max_length=30, choices=CHECK_TYPES)
    passed = models.BooleanField(default=False)
    details = models.JSONField(default=dict)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routers_onboardingcheck"
        unique_together = ["router", "check_type"]


class ProvisioningAgentRequest(models.Model):
    request_id = models.UUIDField(unique=True)
    key_id = models.CharField(max_length=16)
    action = models.CharField(max_length=50)
    router = models.ForeignKey(NASDevice, on_delete=models.CASCADE, null=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routers_provisioningrequest"
