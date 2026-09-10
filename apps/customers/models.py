from django.db import models
from django.db.models.functions import Lower


class Customer(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="customers")
    reference = models.SlugField(max_length=40)
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=500, blank=True)
    notes = models.CharField(max_length=2000, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [models.UniqueConstraint(Lower("reference"), "tenant", name="customer_tenant_reference_ci")]
        indexes = [models.Index(fields=["tenant", "archived_at", "id"], name="customer_tenant_archive_idx")]


class PPPoEPlan(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="pppoe_plans")
    name = models.CharField(max_length=100)
    bandwidth_profile = models.ForeignKey("vouchers.BandwidthProfile", on_delete=models.PROTECT, related_name="pppoe_plans")
    duration_hours = models.PositiveIntegerField()
    price = models.PositiveIntegerField(help_text="NGN kobo; manual renewal does not record a payment")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [models.CheckConstraint(condition=models.Q(duration_hours__gte=1, duration_hours__lte=8760), name="pppoe_plan_duration_range")]


class PPPoEService(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="pppoe_services")
    customer = models.OneToOneField(Customer, on_delete=models.PROTECT, related_name="pppoe_service")
    plan = models.ForeignKey(PPPoEPlan, on_delete=models.PROTECT, related_name="services")
    router = models.ForeignKey("routers.NASDevice", on_delete=models.PROTECT, related_name="pppoe_services")
    username = models.CharField(max_length=50, unique=True)
    password_hash = models.CharField(max_length=256)
    rate_limit = models.CharField(max_length=30)
    period_hours = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    suspended = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    disconnect_before = models.DateTimeField(null=True, blank=True)
    disconnect_state = models.CharField(max_length=20, default="not_checked", choices=[("not_checked","Not checked"),("pending","Pending"),("acknowledged","Acknowledged"),("clear","Clear"),("failed","Failed")])
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["lease_until", "last_reconciled_at"], name="pppoe_reconcile_idx")]
