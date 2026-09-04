from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with role support."""

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    is_platform_admin = models.BooleanField(default=False)

    class Meta:
        db_table = "accounts_user"

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
        return "user"
