from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ["username", "email", "first_name", "last_name", "is_platform_admin", "is_active"]
    list_filter = ["is_platform_admin", "is_active"]
    search_fields = ["username", "email"]
    fieldsets = UserAdmin.fieldsets + (
        ("Additional Info", {"fields": ("phone", "is_platform_admin")}),
    )
