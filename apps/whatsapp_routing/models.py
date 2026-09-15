from django.db import models
from django.utils import timezone
import hmac
import hashlib
import secrets
import uuid


def new_entry_selector():
    return secrets.token_urlsafe(32)


class TenantWhatsAppRoute(models.Model):
    display_number = models.CharField(max_length=16, blank=True, default='', db_default='')
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="whatsapp_route")
    phone_number_id = models.CharField(max_length=100)
    access_token_encrypted = models.TextField()
    webhook_token = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "whatsapp_tenantwhatsapproute"

    def __str__(self):
        return f"WhatsApp Route: {self.tenant.name}"

    def generate_route_token(self):
        """Generate HMAC-signed route token."""
        from apps.subscriptions.entitlements import require_whatsapp
        require_whatsapp(self.tenant)
        selector = secrets.token_hex(8)
        signature = hmac.new(
            self.webhook_token.encode(),
            selector.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        return f"{selector}.{signature}"

    @staticmethod
    def resolve_route_token(token):
        """Resolve a route token to its tenant."""
        try:
            selector, signature = token.split(".")
            routes = TenantWhatsAppRoute.objects.filter(is_active=True)
            for route in routes:
                expected = hmac.new(
                    route.webhook_token.encode(),
                    selector.encode(),
                    hashlib.sha256,
                ).hexdigest()[:16]
                if hmac.compare_digest(signature, expected):
                    from apps.subscriptions.entitlements import whatsapp_allowed
                    return route.tenant if whatsapp_allowed(route.tenant) else None
        except (ValueError, AttributeError):
            pass
        return None


class WhatsAppSenderBinding(models.Model):
    phone_number = models.CharField(max_length=20)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="whatsapp_bindings")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "whatsapp_senderbinding"
        unique_together = ["phone_number"]


class SharedWhatsAppEndpoint(models.Model):
    verification_attempt = models.UUIDField(null=True)
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    phone_number_id = models.CharField(max_length=100)
    display_number = models.CharField(max_length=16)
    access_token_encrypted = models.TextField()
    is_active = models.BooleanField(default=False)
    version = models.UUIDField(default=uuid.uuid4)
    verified_at = models.DateTimeField(null=True, blank=True)
    hash_key_fingerprint = models.CharField(max_length=64, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='wa_shared_endpoint_singleton')]


class TenantWhatsAppEntryRoute(models.Model):
    reminder_preferences = models.JSONField(default=dict, blank=True)
    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.PROTECT, related_name='whatsapp_entry_route')
    selector = models.CharField(max_length=64, unique=True, default=new_entry_selector)
    version = models.UUIDField(default=uuid.uuid4)
    revoked_at = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WhatsAppRoutedSender(models.Model):
    endpoint = models.ForeignKey(SharedWhatsAppEndpoint, on_delete=models.PROTECT)
    route = models.ForeignKey(TenantWhatsAppEntryRoute, on_delete=models.PROTECT)
    customer_hash = models.CharField(max_length=64)
    version = models.UUIDField(default=uuid.uuid4)
    endpoint_version = models.UUIDField()
    route_selector = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    last_activity_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['endpoint', 'customer_hash'], name='wa_endpoint_customer_unique')]


class WhatsAppRoutingHold(models.Model):
    binding = models.ForeignKey(WhatsAppRoutedSender, on_delete=models.PROTECT, related_name='purchase_holds')
    binding_version = models.UUIDField()
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT)
    reference = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)


class WhatsAppInboundEvent(models.Model):
    """Authenticated receipt; ready means routed, not replied to or fulfilled."""
    endpoint = models.ForeignKey(SharedWhatsAppEndpoint, on_delete=models.PROTECT)
    phone_number_id = models.CharField(max_length=100)
    event_key = models.CharField(max_length=64, unique=True)
    message_id = models.CharField(max_length=512)
    kind = models.CharField(max_length=10)
    provider_timestamp = models.PositiveBigIntegerField()
    customer_hash = models.CharField(max_length=64)
    payload_fingerprint = models.CharField(max_length=64)
    payload_encrypted = models.TextField()
    endpoint_version = models.UUIDField()
    binding = models.ForeignKey(WhatsAppRoutedSender, null=True, on_delete=models.PROTECT)
    binding_version = models.UUIDField(null=True)
    tenant = models.ForeignKey('tenants.Tenant', null=True, on_delete=models.PROTECT)
    state = models.CharField(max_length=16, choices=[(s, s) for s in ('ready', 'blocked', 'stale', 'unsupported', 'status', 'conflict')])
    reason = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    duplicate_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=['state', 'received_at'], name='wa_inbox_state_received')]


class WhatsAppSenderWatermark(models.Model):
    endpoint = models.ForeignKey(SharedWhatsAppEndpoint, on_delete=models.PROTECT)
    phone_number_id = models.CharField(max_length=100)
    customer_hash = models.CharField(max_length=64)
    provider_timestamp = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['endpoint', 'phone_number_id', 'customer_hash'], name='wa_sender_watermark_unique')]


class WhatsAppConversation(models.Model):
    last_event_timestamp = models.PositiveBigIntegerField(default=0)
    binding = models.OneToOneField(WhatsAppRoutedSender, on_delete=models.PROTECT)
    binding_version = models.UUIDField()
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT)
    state = models.CharField(max_length=20, default='menu')
    menu = models.JSONField(default=list)
    menu_offset = models.PositiveIntegerField(default=0)
    selected_terms = models.JSONField(null=True)
    reminders_opt_in = models.BooleanField(default=False)


class WhatsAppProcessedEvent(models.Model):
    event = models.OneToOneField(WhatsAppInboundEvent, on_delete=models.PROTECT, related_name='processing')
    outcome = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)


class WhatsAppOrder(models.Model):
    next_reminder_check_at = models.DateTimeField(default=timezone.now, db_index=True)
    source_event = models.OneToOneField(WhatsAppInboundEvent, on_delete=models.PROTECT)
    conversation = models.ForeignKey(WhatsAppConversation, on_delete=models.PROTECT)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT)
    endpoint = models.ForeignKey(SharedWhatsAppEndpoint, on_delete=models.PROTECT)
    endpoint_version = models.UUIDField()
    phone_number_id = models.CharField(max_length=100)
    customer_hash = models.CharField(max_length=64)
    recipient_encrypted = models.TextField()
    payment = models.OneToOneField('vouchers.PaymentTransaction', on_delete=models.PROTECT, related_name='whatsapp_order')
    payment_secret_encrypted = models.TextField()
    hold = models.OneToOneField(WhatsAppRoutingHold, on_delete=models.PROTECT)
    state = models.CharField(max_length=20, default='new')
    checkout_encrypted = models.TextField(blank=True)
    claim = models.UUIDField(null=True)
    started_at = models.DateTimeField(null=True)
    next_check_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    reminders_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['state', 'next_check_at'], name='wa_order_state_check')]


class WhatsAppOutbound(models.Model):
    context = models.JSONField(default=dict)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dedup_key = models.CharField(max_length=160, unique=True)
    endpoint = models.ForeignKey(SharedWhatsAppEndpoint, on_delete=models.PROTECT)
    endpoint_version = models.UUIDField()
    phone_number_id = models.CharField(max_length=100)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT, null=True)
    customer_hash = models.CharField(max_length=64)
    binding_version = models.UUIDField(null=True)
    source_event = models.ForeignKey(WhatsAppInboundEvent, on_delete=models.PROTECT, null=True)
    order = models.ForeignKey(WhatsAppOrder, on_delete=models.PROTECT, null=True, related_name='outbound')
    kind = models.CharField(max_length=24, default='reply')
    payload_encrypted = models.TextField()
    state = models.CharField(max_length=20, default='pending')
    provider_message_id = models.CharField(max_length=512, blank=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    claim = models.UUIDField(null=True)
    started_at = models.DateTimeField(null=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['state', 'next_attempt_at'], name='wa_outbox_state_attempt')]
