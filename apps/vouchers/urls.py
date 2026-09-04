from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.include_format_suffixes = False
router.register("plans", views.InternetPlanViewSet, basename="plan")
router.register("vouchers", views.VoucherViewSet, basename="voucher")
router.register("payments/transactions", views.PaymentTransactionViewSet, basename="payment-transaction")

urlpatterns = [
    path("", include(router.urls)),
]
