import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from .staff_models import StaffAssignment, StaffInvitation  # noqa: F401


class User(AbstractUser):
    """Custom user model with role support."""

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    is_platform_admin = models.BooleanField(default=False)
    # Null until the email address has been confirmed. Defaults to "verified now"
    # for accounts created through internal flows (agents, staff invitations,
    # superuser, tests) — ONLY public registration (RegisterSerializer) starts
    # unverified and must confirm via OTP. See apps.accounts.verification.
    email_verified_at = models.DateTimeField(null=True, blank=True, default=timezone.now)

    class Meta:
        db_table = "accounts_user"
        constraints = [models.UniqueConstraint(Lower("email"), name="unique_user_email_casefold")]

    def __str__(self):
        return self.username

    @property
    def role(self):
        if self.is_platform_admin:
            return "platform_admin"
        if hasattr(self, "membership"):
            return self.membership.role
        if hasattr(self, "agent_profile"):
            return "agent"
        if self.staff_assignments.filter(is_active=True, tenant__is_active=True).exists():
            return "platform_staff"
        return "user"


class EmailVerificationCode(models.Model):
    """One-time OTP emailed to a user to confirm ownership of their address.

    Only the HMAC-SHA256 hash of the 6-digit code is stored. Codes expire after
    10 minutes, allow at most 5 wrong attempts, and are invalidated (consumed)
    as soon as a newer code is issued for the same user.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_codes"
    )
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_email_verification_code"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"email verification for {self.user.username} ({'consumed' if self.consumed_at else 'outstanding'})"


class RegistrationEmailChallenge(models.Model):
    """Temporary email ownership proof, before any user or workspace exists."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    code_hash = models.CharField(max_length=64, blank=True)
    token_hash = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'accounts_registration_email_challenge'
        indexes = [models.Index(fields=['expires_at'], name='registration_expiry_idx')]
