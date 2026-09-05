from rest_framework.permissions import BasePermission


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_platform_admin
        )


class IsTenantOwner(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, "membership")
            and request.user.membership.role == "owner"
            and request.user.membership.tenant.is_active
        )


class IsTenantManager(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_authenticated and not hasattr(request.user, "membership"):
            from .api import assigned_tenant
            from rest_framework.exceptions import PermissionDenied
            try:
                assigned_tenant(request, view)
                return True
            except PermissionDenied:
                return False
        return (
            request.user.is_authenticated
            and hasattr(request.user, "membership")
            and request.user.membership.role in ("owner", "manager")
            and request.user.membership.tenant.is_active
        )


class IsAgent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, "agent_profile")
            and request.user.agent_profile.status == "active"
            and request.user.agent_profile.tenant.is_active
        )
