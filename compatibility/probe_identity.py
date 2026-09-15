"""Reproduce current identity behavior in a disposable in-memory database.

Run from the backend directory with: python compatibility/probe_identity.py
This is an observation tool, not a compatibility pass/fail gate. It never uses
the configured application database or prints tokens/passwords/customer data.
"""
import json
import os
import sys
from pathlib import Path


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_settings'
    from django.conf import settings

    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    settings.ALLOWED_HOSTS = ['testserver']
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    settings.REGISTRATION_EMAIL_BACKEND = settings.EMAIL_BACKEND
    settings.RESEND_API_KEY = ''

    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from rest_framework.test import APIClient
    from apps.accounts.models import User
    from apps.tenants.models import Tenant, TenantMembership
    from apps.tenants.serializers import TenantMembershipSerializer

    assert connection.vendor == 'sqlite' and connection.settings_dict['NAME'] == ':memory:'
    call_command('migrate', verbosity=0, interactive=False)
    owner = User.objects.create_user('audit-owner', email='owner@example.invalid', password='Audit-fixture-only-123')
    tenant = Tenant.objects.create(name='Audit tenant', slug='audit-tenant')
    TenantMembership.objects.create(user=owner, tenant=tenant, role='owner')
    client = APIClient()
    results = {}
    for label, identifier in [('username_login', owner.username), ('email_login', owner.email)]:
        response = client.post('/api/v1/auth/login/', {
            'username': identifier, 'password': 'Audit-fixture-only-123',
        }, format='json')
        results[label] = response.status_code

    client.force_authenticate(owner)
    verification_before = owner.email_verified_at
    response = client.patch('/api/v1/auth/user/', {'email': 'changed@example.invalid'}, format='json')
    owner.refresh_from_db()
    results['email_change'] = {
        'status': response.status_code,
        'changed': owner.email == 'changed@example.invalid',
        'verification_timestamp_preserved': owner.email_verified_at == verification_before,
    }
    results['membership_has_active_flag'] = any(f.name == 'is_active' for f in TenantMembership._meta.fields)

    admin = User.objects.create_user('audit-admin', email='admin@example.invalid', is_platform_admin=True)
    membership = TenantMembershipSerializer(data={'user': admin.pk, 'tenant': tenant.pk, 'role': 'owner'})
    results['platform_admin_membership_accepted'] = membership.is_valid()
    client.force_authenticate(admin)
    response = client.post('/api/v1/tenants/', {'name': 'Created via API', 'slug': 'created-via-api'}, format='json')
    created = Tenant.objects.filter(slug='created-via-api').first()
    results['platform_tenant_create'] = {
        'status': response.status_code,
        'owner_memberships': created.memberships.filter(role='owner').count() if created else None,
    }
    print(json.dumps(results, indent=2, sort_keys=True))
    connection.close()


if __name__ == '__main__':
    main()
