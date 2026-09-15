from django.conf import settings
from apps.vouchers.services import PaystackService


def get_paystack_service(tenant=None):
    """Get Paystack service with tenant-specific or global keys."""
    if tenant and hasattr(tenant, "settings") and tenant.settings.paystack_secret_key:
        return PaystackService(secret_key=tenant.settings.paystack_secret_key)
    return PaystackService(secret_key=settings.PAYSTACK_SECRET_KEY)


def get_paystack_secret(tenant=None):
    """Return the same signing secret used by the tenant's Paystack client."""
    return get_paystack_service(tenant).secret_key


def get_payment_paystack_service(payment):
    """WhatsApp orders retain the account that initialized their transaction."""
    order = getattr(payment, 'whatsapp_order', None)
    if order:
        from apps.routers.secret_store import secret_store
        return PaystackService(secret_key=secret_store.decrypt(order.payment_secret_encrypted))
    return get_paystack_service(payment.tenant)
