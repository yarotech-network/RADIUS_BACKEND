"""Email-first signup: temporary proof followed by one atomic workspace creation."""
import secrets
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.tenants.models import Tenant, TenantMembership
from .models import RegistrationEmailChallenge
from .verification import send_verification_email, registration_console_notice

CODE_TTL = timedelta(minutes=10)
PROOF_TTL = timedelta(minutes=30)
COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5


class RegistrationError(Exception):
    def __init__(self, message, code='invalid_verification', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def digest(record_id, value):
    return salted_hmac('registration-proof', f'{record_id}:{value}', algorithm='sha256').hexdigest()


def request_code(email):
    email = email.strip().lower()
    # Match the generic send response for existing addresses; do not create users.
    if get_user_model().objects.filter(email__iexact=email).exists():
        registration_console_notice("No code generated: this email already belongs to an account. Use Sign in; existing unverified accounts can continue at /verify-email.")
        return
    now = timezone.now()
    with transaction.atomic():
        record, _ = RegistrationEmailChallenge.objects.get_or_create(email=email, defaults={'expires_at': now})
        record = RegistrationEmailChallenge.objects.select_for_update().get(pk=record.pk)
        if record.sent_at and record.sent_at + COOLDOWN > now:
            registration_console_notice("No new code generated: a code was requested within the last 60 seconds. Wait, then select Resend code.")
            return
        code = f'{secrets.randbelow(1000000):06d}'
        record.code_hash = digest(record.pk, code)
        record.token_hash = ''
        record.expires_at = now + CODE_TTL
        record.attempts = 0
        record.sent_at = now
        record.verified_at = record.consumed_at = None
        record.save()
    # Reuse existing Resend/Django delivery; never hold a row lock across HTTP.
    if not send_verification_email(SimpleNamespace(email=email, username='there', pk=record.pk), code):
        RegistrationEmailChallenge.objects.filter(pk=record.pk, code_hash=record.code_hash).update(sent_at=None, expires_at=now)
        raise RegistrationError('We could not send the email. Please try again.', 'delivery_unavailable', 503)


def verify_code(email, code):
    error = None
    token = None
    with transaction.atomic():
        record = RegistrationEmailChallenge.objects.select_for_update().filter(email=email.strip().lower()).first()
        now = timezone.now()
        if not record or record.verified_at or record.consumed_at or record.expires_at <= now:
            error = 'This code is invalid or expired. Request a new code.'
        elif record.attempts >= MAX_ATTEMPTS:
            error = 'Too many incorrect attempts. Request a new code.'
        elif not secrets.compare_digest(record.code_hash, digest(record.pk, code)):
            record.attempts += 1
            record.save(update_fields=['attempts'])
            error = 'Incorrect code. Please check your email and try again.'
        else:
            secret = secrets.token_urlsafe(32)
            record.token_hash = digest(record.pk, secret)
            record.verified_at = now
            record.expires_at = now + PROOF_TTL
            record.save(update_fields=['token_hash', 'verified_at', 'expires_at'])
            token = f'{record.pk}:{secret}'
    # Raise after commit, otherwise failed attempts would roll back.
    if error:
        raise RegistrationError(error)
    return token


@transaction.atomic
def create_workspace(data):
    try:
        record_id, secret = data['registration_token'].split(':', 1)
        record_id = UUID(record_id)
    except (ValueError, TypeError):
        raise RegistrationError('Verify your email again to continue.', 'verification_required')
    record = RegistrationEmailChallenge.objects.select_for_update().filter(pk=record_id).first()
    if (not record or not record.verified_at or record.expires_at <= timezone.now()
            or record.email != data['email'].strip().lower()
            or not secrets.compare_digest(record.token_hash, digest(record.pk, secret))):
        raise RegistrationError('Your email verification expired. Verify your email again.', 'verification_required')
    if record.consumed_at:
        raise RegistrationError('This registration is already complete. Please sign in.', 'registration_complete', 409)
    user = get_user_model().objects.create_user(
        username=data['username'], email=record.email, password=data['password'],
        first_name=data['first_name'], last_name=data['last_name'], phone=data['phone'],
        email_verified_at=record.verified_at,
    )
    tenant = Tenant.objects.create(name=data['tenant_name'], slug=data['workspace_id'], email=record.email, phone=data['phone'])
    TenantMembership.objects.create(user=user, tenant=tenant, role='owner')
    record.consumed_at = timezone.now()
    record.save(update_fields=['consumed_at'])
    return user, tenant
