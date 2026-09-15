from .models import TenantWhatsAppRoute
import hmac
import hashlib
import re
from urllib.parse import quote


def generate_route_url(tenant, base_url="https://wa.me"):
    """Generate wa.me link with route token."""
    from apps.subscriptions.entitlements import whatsapp_allowed
    if not whatsapp_allowed(tenant):
        return None
    try:
        route = TenantWhatsAppRoute.objects.get(tenant=tenant, is_active=True)
        number = route.display_number.lstrip('+')
        if not re.fullmatch(r'[1-9][0-9]{6,14}', number):
            return None
        token = route.generate_route_token()
        return f"{base_url}/{number}?text={quote(token, safe='')}"
    except TenantWhatsAppRoute.DoesNotExist:
        return None


def resolve_route_token(token):
    """Resolve incoming WhatsApp route token to tenant."""
    return TenantWhatsAppRoute.resolve_route_token(token)
