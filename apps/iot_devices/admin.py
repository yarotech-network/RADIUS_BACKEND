from django.contrib import admin
from .models import MacDevice


@admin.register(MacDevice)
class MacDeviceAdmin(admin.ModelAdmin):
    list_display = ["device_name", "mac_address", "plan", "tenant", "is_active", "expires_at"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["device_name", "mac_address"]

    # Lifecycle writes require the scoped/versioned API; admin must not bypass it.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
