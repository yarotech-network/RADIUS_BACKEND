from django.contrib import admin
from .models import NASDevice, RouterAuditEvent, RouterOnboardingCheck, ProvisioningAgentRequest


@admin.register(NASDevice)
class NASDeviceAdmin(admin.ModelAdmin):
    list_display = ["name", "ip_address", "tenant", "onboarding_state", "is_active", "last_seen_at"]
    list_filter = ["onboarding_state", "is_active", "tenant"]
    search_fields = ["name", "ip_address"]
    readonly_fields = ["id", "last_seen_at"]


@admin.register(RouterAuditEvent)
class RouterAuditEventAdmin(admin.ModelAdmin):
    list_display = ["router", "action", "from_state", "to_state", "created_at"]
    list_filter = ["action"]
    search_fields = ["router__name"]
    readonly_fields = ["id", "correlation_id"]


@admin.register(RouterOnboardingCheck)
class RouterOnboardingCheckAdmin(admin.ModelAdmin):
    list_display = ["router", "check_type", "passed", "checked_at"]
    list_filter = ["check_type", "passed"]
    search_fields = ["router__name"]


@admin.register(ProvisioningAgentRequest)
class ProvisioningAgentRequestAdmin(admin.ModelAdmin):
    list_display = ["request_id", "key_id", "action", "router", "created_at"]
    list_filter = ["action"]
    search_fields = ["request_id"]
