from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AuditViewSet, PlatformAuditViewSet, PlatformRouterViewSet, PlatformPaymentViewSet, PlatformStatsView
from .views import PlatformWalletPaymentViewSet, PlatformSubscriptionPaymentViewSet
from apps.tenants.public_api import PublicTenantView, PublicPlansView
from apps.routers.operation_api import RouterOperationViewSet
from apps.payments.recovery_api import PaymentRecoveryViewSet, PaymentDeliveryViewSet
from apps.accounts.staff_api import StaffAssignmentViewSet, StaffInvitationViewSet, AcceptStaffInvitationView, MyStaffAssignmentsViewSet

router = DefaultRouter()
router.include_format_suffixes = False
router.register("payment-recovery", PaymentRecoveryViewSet, basename="payment-recovery")
router.register("payment-deliveries", PaymentDeliveryViewSet, basename="payment-delivery")
router.register("router-operations", RouterOperationViewSet, basename="router-operation")
router.register("staff/assignments", MyStaffAssignmentsViewSet, basename="my-staff-assignment")
router.register("platform/staff-assignments", StaffAssignmentViewSet, basename="staff-assignment")
router.register("platform/staff-invitations", StaffInvitationViewSet, basename="staff-invitation")
router.register("audit-events", AuditViewSet, basename="audit-event")
router.register("platform/audit-events", PlatformAuditViewSet, basename="platform-audit")
router.register("platform/routers", PlatformRouterViewSet, basename="platform-router")
router.register("platform/payments", PlatformPaymentViewSet, basename="platform-payment")
router.register("platform/wallet-payments", PlatformWalletPaymentViewSet, basename="platform-wallet-payment")
router.register("platform/subscription-payments", PlatformSubscriptionPaymentViewSet, basename="platform-subscription-payment")
urlpatterns = [
    path("staff-invitations/accept/", AcceptStaffInvitationView.as_view(), name="staff-invitation-accept"),
    path("", include(router.urls)),
    path("platform/dashboard/", PlatformStatsView.as_view(), name="platform-dashboard"),
    path("public/tenants/<slug:slug>/", PublicTenantView.as_view(), name="public-tenant"),
    path("public/tenants/<slug:slug>/plans/", PublicPlansView.as_view(), name="public-plans"),
]
