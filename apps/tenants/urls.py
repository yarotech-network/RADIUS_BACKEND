from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.include_format_suffixes = False
router.register("tenants", views.TenantViewSet, basename="tenant")
router.register("tenant-memberships", views.TenantMembershipViewSet, basename="tenant-membership")

urlpatterns = [
    path("tenants/settings/", views.TenantSettingView.as_view(), name="tenant-settings"),
    path("", include(router.urls)),
]
