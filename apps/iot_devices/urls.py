from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .radius_api import HotspotRadiusBoundary, HotspotPostAuth

router = DefaultRouter()
router.include_format_suffixes = False
router.register("iot-devices", views.MacDeviceViewSet, basename="iot-device")

urlpatterns = [
    path("radius/hotspot/authorize/", HotspotRadiusBoundary.as_view(), name="hotspot-radius-authorize"),
    path("radius/hotspot/post-auth/", HotspotPostAuth.as_view(), name="hotspot-radius-post-auth"),
    path("", include(router.urls)),
]
