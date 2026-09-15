"""Identity proof and setup delivery. Database writes never span provider calls."""
import logging
import secrets
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import get_connection, send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.exceptions import ValidationError

from .models import EmailChangeRequest

logger = logging.getLogger(__name__)


def deliver_identity_email(email, subject, text):
    try:
        backend = getattr(settings, 'REGISTRATION_EMAIL_BACKEND', '')
        if not backend and getattr(settings, 'RESEND_API_KEY', ''):
            response = requests.post('https://api.resend.com/emails', json={
                'from': settings.DEFAULT_FROM_EMAIL, 'to': [email], 'subject': subject, 'text': text,
            }, headers={'Authorization': f'Bearer {settings.RESEND_API_KEY}'},
                timeout=settings.EMAIL_TIMEOUT)
            return response.status_code in (200, 201) and bool(response.json().get('id'))
        return send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [email],
                         connection=get_connection(backend or settings.EMAIL_BACKEND)) == 1
    except Exception:
        # Provider exceptions can include recipient addresses and request secrets.
        logger.warning('Identity email delivery failed')
        return False


def send_owner_setup(user):
    if not user.owner_setup_pending or not user.is_active:
        return False
    url = settings.PASSWORD_RESET_FRONTEND_URL.format(
        uid=urlsafe_base64_encode(force_bytes(user.pk)),
        token=default_token_generator.make_token(user),
    )
    return deliver_identity_email(user.email, 'Set up your Yarotech account',
        f'Your workspace owner account is ready. Choose your password using this link:\n\n{url}\n\n'
        'If you did not expect this invitation, ignore this message.')


def change_digest(user_id, email, code):
    return salted_hmac('email-change', f'{user_id}:{email}:{code}', algorithm='sha256').hexdigest()


def request_email_change(user, email, password):
    User = get_user_model()
    email = email.strip().lower()
    now = timezone.now()
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if not user.is_active or not user.check_password(password):
            raise ValidationError({'password': 'Enter your current password.'})
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError({'email': 'This address is unavailable.'})
        current = EmailChangeRequest.objects.filter(user=user).first()
        if current and current.requested_at > now - timedelta(seconds=60):
            raise ValidationError('Wait one minute before requesting another code.')
        code = f'{secrets.randbelow(1000000):06d}'
        record, _ = EmailChangeRequest.objects.update_or_create(user=user, defaults={
            'email': email, 'code_hash': change_digest(user.pk, email, code),
            'expires_at': now + timedelta(minutes=10), 'requested_at': now,
            'attempts': 0, 'consumed_at': None,
        })
    sent = deliver_identity_email(email, 'Confirm your new email address',
        f'Your email change code is: {code}\n\nIt expires in 10 minutes. '
        'Your current email stays unchanged until you confirm this code.')
    if not sent:
        EmailChangeRequest.objects.filter(pk=record.pk, code_hash=record.code_hash).update(
            expires_at=now, requested_at=now - timedelta(seconds=60))
    return sent


def confirm_email_change(user, code):
    User = get_user_model()
    error = None
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        record = EmailChangeRequest.objects.select_for_update().filter(user=user).first()
        now = timezone.now()
        if not user.is_active or not record or record.consumed_at or record.expires_at <= now or record.attempts >= 5:
            error = 'This code is invalid or expired. Request another code.'
        elif not secrets.compare_digest(record.code_hash, change_digest(user.pk, record.email, code)):
            record.attempts += 1
            record.save(update_fields=['attempts'])
            error = 'Incorrect code.'
        elif User.objects.filter(email__iexact=record.email).exclude(pk=user.pk).exists():
            error = 'This address is unavailable.'
        else:
            try:
                with transaction.atomic():
                    user.email = record.email
                    user.email_verified_at = now
                    user.save(update_fields=['email', 'email_verified_at'])
                    record.consumed_at = now
                    record.save(update_fields=['consumed_at'])
            except IntegrityError:
                error = 'This address is unavailable.'
    # Raise only after commit so unsuccessful attempts cannot roll back.
    if error:
        raise ValidationError(error)
    return user
