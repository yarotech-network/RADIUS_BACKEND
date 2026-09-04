from .models import TenantWhatsAppRoute
import hmac
import hashlib


def generate_route_url(tenant, base_url="https://wa.me"):
    """Generate wa.me link with route token."""
    try:
        route = TenantWhatsAppRoute.objects.get(tenant=tenant, is_active=True)
        token = route.generate_route_token()
        return f"{base_url}/{route.phone_number_id}?text={token}"
    except TenantWhatsAppRoute.DoesNotExist:
        return None


def resolve_route_token(token):
    """Resolve incoming WhatsApp route token to tenant."""
    return TenantWhatsAppRoute.resolve_route_token(token)
