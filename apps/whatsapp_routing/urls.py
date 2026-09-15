from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .shared_api import SharedEndpointView, EntryRouteView, VerifyEndpointView
from .webhook import whatsapp_webhook
from .workflow_api import ReminderSettingsView, OrderRecoveryList, OrderRecoveryAction

router = DefaultRouter()
router.include_format_suffixes = False
router.register("whatsapp/routes", views.WhatsAppRouteViewSet, basename="whatsapp-route")

urlpatterns = [
    path('whatsapp/reminders/', ReminderSettingsView.as_view(), name='whatsapp-reminders'),
    path('whatsapp/orders/', OrderRecoveryList.as_view(), name='whatsapp-orders'),
    path('whatsapp/orders/<int:pk>/recover/', OrderRecoveryAction.as_view(), name='whatsapp-order-recovery'),
    path('platform/whatsapp/shared-endpoint/verify/', VerifyEndpointView.as_view(), name='whatsapp-verify-endpoint'),
    path('whatsapp/webhook/', whatsapp_webhook, name='whatsapp-webhook'),
    path('platform/whatsapp/shared-endpoint/', SharedEndpointView.as_view(), name='whatsapp-shared-endpoint'),
    path('whatsapp/entry-route/', EntryRouteView.as_view(), name='whatsapp-entry-route'),
    path("", include(router.urls)),
]
