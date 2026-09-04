from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.include_format_suffixes = False
router.register("pricing", views.SubscriptionPlanViewSet, basename="subscription-plan")

urlpatterns = [
    path("", include(router.urls)),
    path("subscriptions/", views.TenantSubscriptionView.as_view(), name="tenant-subscription"),
    path("subscriptions/checkout/", views.SubscriptionCheckoutView.as_view(), name="subscription-checkout"),
    path(
        "subscriptions/payments/<str:reference>/",
        views.SubscriptionPaymentStatusView.as_view(),
        name="subscription-payment-status",
    ),
]
