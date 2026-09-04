from django.contrib import admin
from .models import PaystackWebhookEvent


@admin.register(PaystackWebhookEvent)
class PaystackWebhookEventAdmin(admin.ModelAdmin):
    list_display = ["event_id", "event_type", "processed", "created_at"]
    list_filter = ["event_type", "processed"]
    search_fields = ["event_id"]
