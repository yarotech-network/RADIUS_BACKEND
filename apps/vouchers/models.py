from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets


class BandwidthProfile(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="bandwidth_profiles")
    name = models.CharField(max_length=100)
    upload_kbps = models.PositiveIntegerField()
    download_kbps = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(upload_kbps__gte=1, upload_kbps__lte=10000000), name="bandwidth_upload_range"),
            models.CheckConstraint(condition=models.Q(download_kbps__gte=1, download_kbps__lte=10000000), name="bandwidth_download_range"),
        ]

    @property
    def rate_limit(self):
        return f"{self.upload_kbps}k/{self.download_kbps}k"


class InternetPlan(models.Model):
    bandwidth_profile = models.ForeignKey(BandwidthProfile, null=True, blank=True, on_delete=models.PROTECT, related_name="plans")
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
    rate_limit_snapshot = models.CharField(max_length=20, blank=True, default="", db_default="")
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

    # Access codes are read off a screen or spoken over the phone, so the alphabet drops the
    # look-alikes 0/O, 1/I/L, 5/S and 9 (vs. g/q when handwritten). 8 characters over 28 symbols
    # ≈ 38 bits, which is ample for a single-use hotspot voucher behind RADIUS rate limiting.
    ACCESS_CODE_ALPHABET = "ABCDEFGHJKMNPQRTUVWXYZ234678"
    ACCESS_CODE_LENGTH = 8

    @classmethod
    def generate_access_code(cls, prefix=""):
        return prefix + "".join(secrets.choice(cls.ACCESS_CODE_ALPHABET) for _ in range(cls.ACCESS_CODE_LENGTH))

    @classmethod
    def generate_credentials(cls, prefix=""):
        """One code serves as both username and password: the customer only ever handles a
        single access code. Vouchers created before this change keep their separate passwords."""
        code = cls.generate_access_code(prefix)
        return code, code

    @property
    def access_code(self):
        """The single customer-facing code, or None when the voucher has a separate password."""
        return self.username if self.password == self.username else None

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
    verified_at = models.DateTimeField(null=True, blank=True)
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
