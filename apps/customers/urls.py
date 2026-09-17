from django.urls import path
from .radius_api import PPPoERadiusDecision
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet
from .access_views import CustomerAccessViewSet
from .device_access_views import CustomerDeviceViewSet
from .pppoe_views import PPPoEPlanViewSet, PPPoEServiceViewSet

router = DefaultRouter()
router.include_format_suffixes = False
router.register("customer-access", CustomerAccessViewSet, basename="customer-access")
router.register("customer-devices", CustomerDeviceViewSet, basename="customer-device")
router.register("customers", CustomerViewSet, basename="customer")
router.register("pppoe-plans", PPPoEPlanViewSet, basename="pppoe-plan")
router.register("pppoe-services", PPPoEServiceViewSet, basename="pppoe-service")
urlpatterns = router.urls + [path("radius/pppoe/decision/", PPPoERadiusDecision.as_view(), name="pppoe-radius-decision")]
