from django.db import models
from django.utils import timezone
import re


class MacDevice(models.Model):
    mac_address = models.CharField(max_length=17)
    mac_address_compact = models.CharField(max_length=12, blank=True, default='', db_default='', editable=False)
    status = models.CharField(max_length=12, blank=True, default='', db_default='', choices=[(v,v) for v in ('', 'active', 'suspended', 'expired', 'revoked', 'deleted')])
    version = models.PositiveIntegerField(default=1, db_default=1)
    deleted_at = models.DateTimeField(null=True, blank=True)
    legacy_uuid = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    speed_limit = models.CharField(max_length=50, blank=True, default='', db_default='')
    data_limit_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    issued_terms = models.JSONField(null=True, blank=True)

    device_name = models.CharField(max_length=200)
    plan = models.ForeignKey("vouchers.InternetPlan", on_delete=models.PROTECT, related_name="mac_devices", null=True, blank=True)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="mac_devices")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    router = models.ForeignKey("routers.NASDevice", on_delete=models.PROTECT, null=True, blank=True, related_name="mac_devices")
    access_type = models.CharField(max_length=16, choices=[("permanent", "Permanent"), ("timed", "Time limited")], default="timed")
    vlan_id = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iot_macdevice"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tenant", "mac_address_compact"], name="iot_tenant_mac_idx")]
        constraints = [models.UniqueConstraint(fields=['mac_address_compact'],
            condition=models.Q(is_active=True) & ~models.Q(mac_address_compact=''), name='iot_active_mac_unique')]


    def __str__(self):
        return f"{self.device_name} ({self.mac_address})"

    @staticmethod
    def normalize_mac(mac):
        from django.core.exceptions import ValidationError
        compact = re.sub(r'[:.\-\s]', '', str(mac or '')).upper()
        if (not re.fullmatch(r'[0-9A-F]{12}', compact) or compact in ('000000000000', 'FFFFFFFFFFFF')
            or int(compact[:2], 16) & 1):
            raise ValidationError('Enter a valid unicast MAC address; zero, broadcast and multicast addresses are not allowed.')
        return ':'.join(compact[i:i+2] for i in range(0,12,2))

    def save(self, *args, **kwargs):
        self.mac_address = self.normalize_mac(self.mac_address)
        self.mac_address_compact = self.mac_address.replace(':', '')
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'mac_address', 'mac_address_compact'}
        return super().save(*args, **kwargs)

    @property
    def configured_status(self):
        if self.deleted_at or self.status == 'deleted':
            return 'deleted'
        if self.status in ('revoked', 'expired', 'suspended'):
            return self.status
        return 'active' if self.is_active else 'suspended'

    @property
    def effective_status(self):
        state = self.configured_status
        if state == 'active' and self.access_type == 'timed' and (not self.expires_at or self.expires_at <= timezone.now()):
            return 'expired'
        return state


class DeviceRenewal(models.Model):
    device = models.ForeignKey(MacDevice, on_delete=models.PROTECT, related_name='renewals')
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT)
    actor = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL)
    previous_expiry = models.DateTimeField(null=True)
    expires_at = models.DateTimeField()
    terms = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
