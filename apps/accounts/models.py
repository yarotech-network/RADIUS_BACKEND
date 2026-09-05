from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from .staff_models import StaffAssignment, StaffInvitation  # noqa: F401


class User(AbstractUser):
    """Custom user model with role support."""

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    is_platform_admin = models.BooleanField(default=False)

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
