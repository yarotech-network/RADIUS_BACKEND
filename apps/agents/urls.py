from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .auth_views import AgentLoginView, AgentDashboardView

router = DefaultRouter()
router.include_format_suffixes = False
router.register("agents", views.AgentProfileViewSet, basename="agent")
router.register("agent/wallet", views.AgentWalletViewSet, basename="agent-wallet")
router.register("agent/vouchers", views.AgentVoucherGenerateView, basename="agent-voucher")

urlpatterns = [
    path("", include(router.urls)),
    path("agent/login/", AgentLoginView.as_view(), name="agent-login"),
    path("agent/dashboard/", AgentDashboardView.as_view(), name="agent-dashboard"),
]
