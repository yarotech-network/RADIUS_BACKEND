from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.include_format_suffixes = False
router.register("iot-devices", views.MacDeviceViewSet, basename="iot-device")

urlpatterns = [
    path("", include(router.urls)),
]
