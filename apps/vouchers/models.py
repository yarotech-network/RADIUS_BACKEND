from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets
import string


class InternetPlan(models.Model):
    name = models.CharField(max_length=100)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="plans")
    price = models.PositiveIntegerField(help_text="Price in kobo")
    duration_hours = models.PositiveIntegerField(help_text="Access duration in hours")
    rate_limit = models.CharField(max_length=20, help_text="e.g., 5M/10M (up/down)")
    data_limit = models.PositiveIntegerField(default=0, help_text="Data limit in MB, 0=unlimited")
    voucher_prefix = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vouchers_internetplan"
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} - {self.get_price_display()}"

    def get_price_display(self):
        return f"\u20a6{self.price / 100:,.0f}"


class Voucher(models.Model):
    STATUS_CHOICES = [
        ("unused", "Unused"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("disabled", "Disabled"),
    ]
    SOURCE_CHOICES = [
        ("admin", "Admin"),
        ("agent", "Agent"),
        ("customer", "Customer"),
    ]

    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=50)
    plan = models.ForeignKey(InternetPlan, on_delete=models.PROTECT, related_name="vouchers")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="vouchers")
    agent = models.ForeignKey("agents.AgentProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="unused")
    generation_source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="admin")
    device_limit = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vouchers_voucher"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.username} ({self.status})"

    @staticmethod
    def generate_credentials(prefix=""):
        alphabet = string.ascii_letters + string.digits
        username = prefix + "".join(secrets.choice(alphabet) for _ in range(8))
        password = "".join(secrets.choice(alphabet) for _ in range(12))
        return username, password

    def activate(self):
        activated_at = timezone.now()
        self.status = "active"
        self.activated_at = activated_at
        self.expires_at = activated_at + timezone.timedelta(hours=self.plan.duration_hours)
        self.save(update_fields=["status", "activated_at", "expires_at"])

    def expire(self):
        self.status = "expired"
        self.save(update_fields=["status"])


class PaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("abandoned", "Abandoned"),
    ]

    reference = models.CharField(max_length=100, unique=True)
    amount = models.PositiveIntegerField(help_text="Amount in kobo")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    voucher = models.OneToOneField(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name="payment")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey(InternetPlan, on_delete=models.SET_NULL, null=True, blank=True)
    paystack_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vouchers_paymenttransaction"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.get_status_display()}"


# === FreeRADIUS SQL Tables (read-only in Django) ===

class Radcheck(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=64)
    attribute = models.CharField(max_length=64)
    op = models.CharField(max_length=2)
    value = models.CharField(max_length=253)

    class Meta:
        db_table = "radcheck"
        managed = False  # Django won't create/modify this table


class Radreply(models.Model):
    username = models.CharField(max_length=64)
    attribute = models.CharField(max_length=64)
    op = models.CharField(max_length=2)
    value = models.CharField(max_length=253)

    class Meta:
        db_table = "radreply"
        managed = False


class Radacct(models.Model):
    radacctid = models.BigAutoField(primary_key=True)
    sessionid = models.CharField(max_length=64)
    username = models.CharField(max_length=64)
    nasipaddress = models.GenericIPAddressField()
    nasportid = models.CharField(max_length=32, null=True)
    acctstarttime = models.DateTimeField(null=True)
    acctstoptime = models.DateTimeField(null=True)
    acctinputoctets = models.BigIntegerField(default=0)
    acctoutputoctets = models.BigIntegerField(default=0)
    acctsessiontime = models.IntegerField(default=0)
    acctterminatecause = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = "radacct"
        managed = False


class Radpostauth(models.Model):
    username = models.CharField(max_length=64)
    pass_reply = models.CharField(max_length=64)
    authdate = models.DateTimeField()

    class Meta:
        db_table = "radpostauth"
        managed = False
