from django.urls import path
from . import views
from .webhooks import paystack_webhook

urlpatterns = [
    path("buy/", views.InitializePaymentView.as_view(), name="buy-voucher"),
    path("payments/callback/", views.PaymentCallbackView.as_view(), name="payment-callback"),
    path("payments/paystack/webhook/<str:token>/", paystack_webhook, name="paystack-webhook"),
]
