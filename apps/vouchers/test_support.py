"""Explicit trusted authentication for unrelated issuance regression fixtures."""
from apps.routers.models import NASDevice


def authenticated_activation(voucher):
    address = '192.0.2.42'
    NASDevice.objects.get_or_create(tenant=voucher.tenant, ip_address=address,
        defaults={'name':'Fixture NAS', 'nas_secret':'test-only', 'is_active':True, 'onboarding_state':'active'})
    return voucher.activate(credential_verified=True, nas_ip_address=address)
