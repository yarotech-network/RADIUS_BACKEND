from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .access_api import SubscriptionAccessView

router = DefaultRouter()
router.include_format_suffixes = False
router.register("pricing", views.SubscriptionPlanViewSet, basename="subscription-plan")

router.register("platform/business-plans", views.BusinessPlanViewSet, basename="business-plan")

urlpatterns = [
    path("subscriptions/access/", SubscriptionAccessView.as_view(), name="subscription-access"),
    path("", include(router.urls)),
    path("subscriptions/", views.TenantSubscriptionView.as_view(), name="tenant-subscription"),
    path("subscriptions/checkout/", views.SubscriptionCheckoutView.as_view(), name="subscription-checkout"),
    path("subscriptions/payments/<str:reference>/verify/", views.SubscriptionPaymentVerifyView.as_view(), name="subscription-payment-verify"),
    path(
        "subscriptions/payments/<str:reference>/",
        views.SubscriptionPaymentStatusView.as_view(),
        name="subscription-payment-status",
    ),
]
