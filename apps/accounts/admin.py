from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import EmailVerificationCode, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = [
        "username", "email", "first_name", "last_name",
        "is_platform_admin", "email_verified", "is_active",
    ]
    list_filter = ["is_platform_admin", "is_active"]
    search_fields = ["username", "email"]
    fieldsets = UserAdmin.fieldsets + (
        ("Additional Info", {"fields": ("phone", "is_platform_admin", "email_verified_at")}),
    )
    readonly_fields = ("email_verified_at",)

    @admin.display(boolean=True, description="Verified")
    def email_verified(self, obj):
        return obj.email_verified_at is not None


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "expires_at", "attempts", "consumed_at"]
    list_filter = ["consumed_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = [f.name for f in EmailVerificationCode._meta.fields]
    list_select_related = ["user"]
