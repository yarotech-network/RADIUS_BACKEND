from django.contrib import admin
from .models import MacDevice


@admin.register(MacDevice)
class MacDeviceAdmin(admin.ModelAdmin):
    list_display = ["device_name", "mac_address", "plan", "tenant", "is_active", "expires_at"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["device_name", "mac_address"]
