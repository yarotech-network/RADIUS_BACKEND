from django.db import models
from django.conf import settings


class Tenant(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_platform_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_tenant"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("manager", "Manager"),
        ("staff", "Staff"),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="staff")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenants_membership"
        unique_together = ["user", "tenant"]

    def __str__(self):
        return f"{self.user.username} -> {self.tenant.name} ({self.role})"


class TenantSetting(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="settings")
    paystack_secret_key = models.CharField(max_length=255, blank=True)
    paystack_public_key = models.CharField(max_length=255, blank=True)
    agent_commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    voucher_prefix = models.CharField(max_length=10, blank=True)
    max_funding_amount = models.PositiveIntegerField(default=100000)  # in kobo
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_setting"

    def __str__(self):
        return f"Settings for {self.tenant.name}"
