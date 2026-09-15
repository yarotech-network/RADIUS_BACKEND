from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets
from django.db.models.functions import Lower
from .code_formats import PLAN_FORMAT_CHOICES


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


class InternetPlanQuerySet(models.QuerySet):
    def delete(self):
        from django.db import transaction
        from .terms import freeze_plan_contracts
        with transaction.atomic(using=self.db):
            rows = list(self.select_for_update().order_by('pk'))
            for plan in rows:
                freeze_plan_contracts(plan)
            count = self.filter(pk__in=[p.pk for p in rows], archived_at__isnull=True).update(
                archived_at=timezone.now(), is_active=False, is_public=False, agent_enabled=False)
        return count, {self.model._meta.label: count}


class InternetPlan(models.Model):
    bandwidth_profile = models.ForeignKey(BandwidthProfile, null=True, blank=True, on_delete=models.PROTECT, related_name="plans")
    name = models.CharField(max_length=100)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="plans")
    price = models.PositiveIntegerField(help_text="Price in kobo")
    duration_hours = models.DecimalField(max_digits=16, decimal_places=6, help_text="Hours; rounded to whole seconds at issuance")
    rate_limit = models.CharField(max_length=50, blank=True, default="", help_text="e.g., 5M/10M (up/down)")
    data_limit = models.PositiveIntegerField(default=0, help_text="Data limit in MB, 0=unlimited")
    voucher_prefix = models.CharField(max_length=10, blank=True)
    voucher_code_format = models.CharField(max_length=20, choices=PLAN_FORMAT_CHOICES, default="legacy")
    is_public = models.BooleanField(default=True, db_default=True)
    agent_enabled = models.BooleanField(default=True, db_default=True)
    plan_type = models.CharField(max_length=20, choices=[('voucher', 'Hotspot voucher'), ('iot_mac', 'IoT / MAC')], default='voucher', db_default='voucher')
    public_router = models.ForeignKey('routers.NASDevice', null=True, blank=True, on_delete=models.PROTECT, related_name='public_internet_plans')
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    objects = InternetPlanQuerySet.as_manager()

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(archived_at__isnull=True) | models.Q(is_active=False, is_public=False, agent_enabled=False), name='archived_plan_not_sellable')]
        db_table = "vouchers_internetplan"
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} - {self.get_price_display()}"

    @property
    def duration_seconds(self):
        from .terms import duration_seconds
        return duration_seconds(self.duration_hours)

    def save(self, *args, **kwargs):
        from django.db import transaction
        from django.core.exceptions import ValidationError
        from .terms import freeze_plan_contracts
        with transaction.atomic():
            if not self._state.adding:
                old = type(self).objects.select_for_update().get(pk=self.pk)
                if old.archived_at and (self.archived_at != old.archived_at or self.is_active or self.is_public or self.agent_enabled):
                    raise ValidationError('Archived plans cannot be reactivated.')
                fields = ('name', 'price', 'duration_hours', 'data_limit', 'rate_limit', 'bandwidth_profile_id', 'plan_type', 'public_router_id')
                if any(getattr(old, f) != getattr(self, f) for f in fields):
                    freeze_plan_contracts(old)
                if old.archived_at:
                    raise ValidationError('Archived plans are read-only.')
            return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        result = type(self).objects.using(using or self._state.db).filter(pk=self.pk).delete()
        self.refresh_from_db()
        return result

    def get_price_display(self):
        return f"\u20a6{self.price / 100:,.0f}"


class Voucher(models.Model):
    customer = models.ForeignKey('customers.Customer', null=True, blank=True, on_delete=models.PROTECT,
        related_name='vouchers')
    purchased_terms = models.JSONField(null=True, blank=True, editable=False)
    issued_duration_seconds = models.PositiveBigIntegerField(null=True, blank=True, editable=False)
    rate_limit_snapshot = models.CharField(max_length=50, blank=True, default="", db_default="")
    STATUS_CHOICES = [
        ("unused", "Unused"),
        ("sold", "Sold"),
        ("used", "Used"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("disabled", "Disabled"),
    ]
    SOURCE_CHOICES = [
        ("admin", "Admin"),
        ("agent", "Agent"),
        ("customer", "Customer"),
    ]

    username = models.CharField(max_length=64, unique=True)
    password = models.CharField(max_length=64)
    plan = models.ForeignKey(InternetPlan, on_delete=models.PROTECT, related_name="vouchers")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="vouchers")
    agent = models.ForeignKey("agents.AgentProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="unused")
    generation_source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="admin")
    device_limit = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    first_used_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_used_at = models.DateTimeField(null=True, blank=True, editable=False)
    used_at = models.DateTimeField(null=True, blank=True, editable=False)
    is_used = models.BooleanField(default=False, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    device_lock_enabled = models.BooleanField(default=False, editable=False)
    bound_device_mac = models.CharField(max_length=17, blank=True, editable=False)
    device_bound_at = models.DateTimeField(null=True, blank=True, editable=False)
    device_bound_nas = models.ForeignKey('routers.NASDevice', null=True, blank=True, on_delete=models.PROTECT, related_name='bound_vouchers', editable=False)
    legacy_provenance = models.JSONField(null=True, blank=True, editable=False, help_text='Import source IDs and retained usage, binding-reset and deletion audit evidence. Not exposed by API.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("username"), name="voucher_username_casefold_unique")]
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
    def generate_access_code(cls, prefix="", code_format="legacy"):
        from .code_formats import generate_code
        return generate_code(prefix, code_format)

    @classmethod
    def generate_credentials(cls, prefix="", code_format="legacy"):
        """One code serves as both username and password: the customer only ever handles a
        single access code. Vouchers created before this change keep their separate passwords."""
        code = cls.generate_access_code(prefix, code_format)
        return code, code

    @property
    def access_code(self):
        """The single customer-facing code, or None when the voucher has a separate password."""
        return self.username if self.password == self.username else None

    def activate(self, *, credential_verified=False, nas_ip_address='', mac_address=''):
        from .lifecycle import finalize_authenticated_voucher
        result = finalize_authenticated_voucher(self.pk, credential_verified=credential_verified,
            nas_ip_address=nas_ip_address, mac_address=mac_address)
        self.refresh_from_db()
        return result['activated']

    def expire(self):
        self.status = "expired"
        self.save(update_fields=["status"])

    @property
    def service_terms(self):
        from .terms import resolved_terms
        return resolved_terms(self)

    def save(self, *args, **kwargs):
        from django.db import transaction
        from django.core.exceptions import ValidationError
        with transaction.atomic():
            if self._state.adding:
                from .terms import snapshot_plan, duration_seconds
                if self.purchased_terms is None:
                    self.plan = InternetPlan.objects.select_for_update().get(pk=self.plan_id)
                    if self.plan.archived_at or not self.plan.is_active or self.plan.plan_type != 'voucher':
                        raise ValidationError('Plan is unavailable for new vouchers.')
                    self.purchased_terms = snapshot_plan(self.plan, self.device_limit)
                if self.issued_duration_seconds is None:
                    self.issued_duration_seconds = self.purchased_terms.get('duration_seconds') or duration_seconds(self.purchased_terms['duration_hours'])
            return super().save(*args, **kwargs)

    def get_price_display(self):
        return f"\u20a6{self.service_terms['price'] / 100:,.0f}"


class PaymentTransaction(models.Model):
    customer = models.ForeignKey('customers.Customer', null=True, blank=True, on_delete=models.PROTECT,
        related_name='purchases')
    purchased_terms = models.JSONField(null=True, blank=True, editable=False)
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
    plan = models.ForeignKey(InternetPlan, on_delete=models.PROTECT, null=True, blank=True)
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
    callingstationid = models.CharField(max_length=64, null=True, blank=True)
    radacctid = models.BigAutoField(primary_key=True)
    sessionid = models.CharField(max_length=64, db_column='acctsessionid')
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
    pass_reply = models.CharField(max_length=64, db_column='reply')
    authdate = models.DateTimeField()

    class Meta:
        db_table = "radpostauth"
        managed = False
