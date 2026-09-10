from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.Model):
    internal_code = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)
    name = models.CharField(max_length=100)
    price = models.PositiveIntegerField(help_text="Price in kobo")
    duration_days = models.PositiveIntegerField()
    features = models.JSONField(default=list)
    max_routers = models.PositiveIntegerField(null=True, blank=True)
    daily_voucher_print_limit = models.PositiveIntegerField(null=True, blank=True)
    whatsapp_enabled = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_plan"
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} - \u20a6{self.price / 100}"


class TenantSubscription(models.Model):
    STATUS_CHOICES = [
        ("trial", "Trial"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ]

    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="trial")
    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    is_trial = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_tenantsubscription"

    def __str__(self):
        return f"{self.tenant.name} - {self.plan.name} ({self.status})"

    @property
    def is_active(self):
        return self.status in ("trial", "active") and self.expires_at > timezone.now()


class SubscriptionPayment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="subscription_payments"
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.PROTECT, related_name="payments"
    )
    subscription = models.ForeignKey(
        TenantSubscription,
        on_delete=models.SET_NULL,
        related_name="payments",
        null=True,
        blank=True,
    )
    reference = models.CharField(max_length=100, unique=True)
    amount = models.PositiveIntegerField()
    plan_terms = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "subscriptions_payment"


class SubscriptionPeriod(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="subscription_periods")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="periods")
    payment = models.OneToOneField(SubscriptionPayment, on_delete=models.PROTECT, null=True, blank=True, related_name="period")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    terms = models.JSONField()
    superseded = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["tenant", "starts_at", "ends_at"], name="subscription_period_lookup")]
        constraints = [models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="subscription_period_positive")]


class VoucherPrintAuthorization(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    # Keep consumed quota even if the voucher is deleted later that day.
    voucher_id = models.PositiveBigIntegerField()
    day = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "day", "voucher_id"], name="unique_daily_voucher_print")]
