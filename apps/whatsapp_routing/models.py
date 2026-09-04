from django.db import models
import hmac
import hashlib
import secrets


class TenantWhatsAppRoute(models.Model):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="whatsapp_route")
    phone_number_id = models.CharField(max_length=100)
    access_token_encrypted = models.CharField(max_length=500)
    webhook_token = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "whatsapp_tenantwhatsapproute"

    def __str__(self):
        return f"WhatsApp Route: {self.tenant.name}"

    def generate_route_token(self):
        """Generate HMAC-signed route token."""
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
                    return route.tenant
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
