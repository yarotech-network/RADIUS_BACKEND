from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .provisioning_views import ProvisioningAgentEndpoint

router = DefaultRouter()
router.include_format_suffixes = False
router.register("routers", views.NASDeviceViewSet, basename="router")

urlpatterns = [
    path("", include(router.urls)),
    path("internal/router-provisioning/", ProvisioningAgentEndpoint.as_view(), name="provisioning-agent"),
]
