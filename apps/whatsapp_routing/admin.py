from django.contrib import admin
from .models import TenantWhatsAppRoute, WhatsAppSenderBinding


@admin.register(TenantWhatsAppRoute)
class TenantWhatsAppRouteAdmin(admin.ModelAdmin):
    list_display = ["tenant", "phone_number_id", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["tenant__name", "phone_number_id"]


@admin.register(WhatsAppSenderBinding)
class WhatsAppSenderBindingAdmin(admin.ModelAdmin):
    list_display = ["phone_number", "tenant", "created_at"]
    search_fields = ["phone_number", "tenant__name"]
