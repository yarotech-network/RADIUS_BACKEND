"""Application access gate; customer RADIUS access is a separate policy."""
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from .models import TenantSubscription


class SubscriptionRequired(PermissionDenied):
    default_detail = 'Your workspace subscription has expired or is unavailable. Payment is required to continue.'
    default_code = 'subscription_required'


ACCESS_ROUTES = {
    'login', 'agent-login', 'logout', 'token-refresh', 'register', 'registration-email',
    'registration-verify', 'registration-create', 'verify-email', 'resend-verification',
    'password-reset', 'password-reset-confirm', 'current-user', 'my-staff-assignment-list',
    'subscription-access', 'tenant-subscription', 'subscription-checkout',
    'subscription-payment-status', 'subscription-payment-verify',
    'subscription-plan-list', 'subscription-plan-detail',
    'payment-callback', 'payment-verify', 'paystack-webhook',
}


def tenant_access(tenant):
    if tenant.is_platform_admin and tenant.is_active:
        return {'required':False, 'status':'platform', 'expires_at':None}
    subscription = TenantSubscription.objects.filter(tenant=tenant).first()
    enabled = bool(tenant.is_active and subscription and subscription.is_active and subscription.started_at <= timezone.now())
    return {'required':not enabled, 'status':subscription.status if subscription else 'missing',
            'expires_at':subscription.expires_at if subscription else None}


def require_tenant_access(tenant):
    if tenant_access(tenant)['required']:
        raise SubscriptionRequired()


def user_access(request, user):
    if user.is_platform_admin and request.headers.get('X-Access-Context', 'platform') == 'platform':
        return {'required':False, 'can_renew':False, 'status':'platform', 'expires_at':None}
    membership = getattr(user, 'membership', None)
    agent = getattr(user, 'agent_profile', None)
    if membership and agent and membership.tenant_id != agent.tenant_id:
        raise PermissionDenied('Conflicting tenant identities require review.')
    if membership:
        result = tenant_access(membership.tenant)
        if not membership.is_active:
            result['required'] = True
        return {**result, 'can_renew':membership.is_active and membership.tenant.is_active and membership.role == 'owner'}
    if agent:
        return {**tenant_access(agent.tenant), 'can_renew':False}
    tenant_id = request.headers.get('X-Tenant-ID', '')
    if tenant_id.isdecimal() and len(tenant_id) <= 19 and int(tenant_id) <= 9223372036854775807:
        from apps.accounts.staff_models import StaffAssignment
        assignment = StaffAssignment.objects.select_related('tenant').filter(user=user, tenant_id=tenant_id, is_active=True).first()
        if assignment:
            return {**tenant_access(assignment.tenant), 'can_renew':False}
    # No workspace has been selected; existing resource permissions still deny operations.
    return {'required':False, 'can_renew':False, 'status':'unassigned', 'expires_at':None}


def enforce_request_access(request, user):
    match = getattr(request, 'resolver_match', None)
    if request.method == 'OPTIONS' or (match and match.url_name in ACCESS_ROUTES):
        return
    if user_access(request, user)['required']:
        raise SubscriptionRequired()
