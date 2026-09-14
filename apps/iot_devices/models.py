from django.db import models


class MacDevice(models.Model):
    mac_address = models.CharField(max_length=17, unique=True)
    device_name = models.CharField(max_length=200)
    plan = models.ForeignKey("vouchers.InternetPlan", on_delete=models.PROTECT, related_name="mac_devices")
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
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.device_name} ({self.mac_address})"

    @staticmethod
    def normalize_mac(mac):
        """Normalize MAC address to XX:XX:XX:XX:XX:XX format."""
        mac = mac.replace("-", ":").replace(".", ":").upper()
        if len(mac) == 12:
            mac = ":".join(mac[i:i+2] for i in range(0, 12, 2))
        return mac
