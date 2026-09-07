from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, datetime, timezone as dt_timezone
from threading import Barrier
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import close_old_connections, transaction
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework.exceptions import PermissionDenied
from apps.tenants.models import Tenant, TenantMembership
from apps.vouchers.models import InternetPlan, Voucher
from apps.routers.models import NASDevice
from apps.whatsapp_routing.models import TenantWhatsAppRoute
from apps.whatsapp_routing.services import generate_route_url
from .models import SubscriptionPlan, SubscriptionPayment, TenantSubscription, SubscriptionPeriod, VoucherPrintAuthorization
from .entitlements import snapshot_plan, entitlement_terms, authorize_print, print_day
from .services import SubscriptionService


class Fixtures:
    def setup_records(self):
        self.tenant = Tenant.objects.create(name="Limits", slug="limits")
        self.owner = get_user_model().objects.create_user(username="owner", email="owner@test.com")
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role="owner")
        self.admin = get_user_model().objects.create_user(username="admin", email="admin@test.com", is_platform_admin=True)
        self.plan = SubscriptionPlan.objects.create(name="Limited", price=100000, duration_days=30, max_routers=1, daily_voucher_print_limit=1, whatsapp_enabled=False)
        now = timezone.now()
        self.sub = TenantSubscription.objects.create(tenant=self.tenant, plan=self.plan, status="active", is_trial=False, started_at=now-timedelta(days=1), expires_at=now+timedelta(days=29))
        SubscriptionPeriod.objects.create(tenant=self.tenant, plan=self.plan, starts_at=self.sub.started_at, ends_at=self.sub.expires_at, terms=snapshot_plan(self.plan))
        internet = InternetPlan.objects.create(tenant=self.tenant, name="Daily", price=100, duration_hours=24, rate_limit="5M/10M")
        self.vouchers = [Voucher.objects.create(tenant=self.tenant, plan=internet, username=f"voucher-{i}", password=f"password-{i}") for i in range(3)]


class EntitlementTests(Fixtures, APITestCase):
    def setUp(self):
        self.setup_records()
        self.client.force_authenticate(self.owner)

    def test_admin_crud_version_conflict_and_protected_deletion(self):
        url = reverse("business-plan-detail", args=[self.plan.pk])
        self.assertEqual(self.client.patch(url, {"name": "Denied"}).status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.patch(url, {"expected_version": 1, "max_routers": 10, "whatsapp_enabled": True, "is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["version"], 2)
        self.assertEqual(entitlement_terms(self.tenant)["max_routers"], 1)
        self.assertEqual(self.client.patch(url, {"expected_version": 1, "name": "Stale"}).status_code, 409)
        self.assertEqual(self.client.delete(url).status_code, 409)
        unused = SubscriptionPlan.objects.create(name="Unused", price=100, duration_days=1)
        self.assertEqual(self.client.delete(reverse("business-plan-detail", args=[unused.pk])).status_code, 204)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("subscription-plan-list")).data["count"], 0)

    @patch("apps.subscriptions.views.get_paystack_service")
    def test_checkout_terms_survive_edit_and_early_renewal(self, provider):
        provider.return_value.initialize_transaction.return_value = {"data": {"authorization_url": "https://checkout.paystack.test/test"}}
        response = self.client.post(reverse("subscription-checkout"), {"plan_id": self.plan.pk})
        self.assertEqual(response.status_code, 200, response.data)
        payment = SubscriptionPayment.objects.get(reference=response.data["reference"])
        self.plan.duration_days = 365
        self.plan.max_routers = 50
        self.plan.save()
        old_end = self.sub.expires_at
        SubscriptionService.complete_payment(payment)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.expires_at, old_end + timedelta(days=30))
        self.assertEqual(payment.period.terms["max_routers"], 1)
        self.assertEqual(entitlement_terms(self.tenant)["max_routers"], 1)
        self.assertFalse(SubscriptionService.complete_payment(payment))
        self.assertEqual(SubscriptionPeriod.objects.filter(payment=payment).count(), 1)

    def test_future_limits_take_effect_at_renewal_boundary(self):
        end = self.sub.expires_at
        payment = SubscriptionPayment.objects.create(tenant=self.tenant, plan=self.plan, reference="renew", amount=100000, plan_terms={**snapshot_plan(self.plan), "max_routers": 4})
        SubscriptionService.complete_payment(payment)
        self.assertEqual(entitlement_terms(self.tenant)["max_routers"], 1)
        with patch("apps.subscriptions.entitlements.timezone.now", return_value=end+timedelta(seconds=1)):
            self.assertEqual(entitlement_terms(self.tenant)["max_routers"], 4)

    def test_router_cap_counts_inactive_and_expired_subscription_blocks_creation(self):
        response = self.client.post("/api/v1/routers/", {"name": "First", "ip_address": "10.0.0.1", "nas_secret": "test-secret", "is_active": False}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.post("/api/v1/routers/", {"name": "Second", "ip_address": "10.0.0.2", "nas_secret": "test-secret"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.sub.expires_at = timezone.now()-timedelta(seconds=1)
        self.sub.save()
        self.assertEqual(self.client.get("/api/v1/routers/").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/routers/", {"name": "Third", "ip_address": "10.0.0.3", "nas_secret": "test-secret"}).status_code, 403)

    def test_print_batch_is_atomic_and_same_day_reprints_are_free(self):
        ids = [item.pk for item in self.vouchers]
        url = "/api/v1/vouchers/authorize-print/"
        response = self.client.post(url, {"voucher_ids": ids[:2]}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(VoucherPrintAuthorization.objects.exists())
        self.assertEqual(self.client.get(f"/api/v1/vouchers/{ids[0]}/print/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/vouchers/{ids[0]}/pdf/").status_code, 403)
        for _ in range(2):
            response = self.client.post(url, {"voucher_ids": [ids[0]]}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["used"], 1)
        self.assertEqual(self.client.get(f"/api/v1/vouchers/{ids[0]}/print/").status_code, 200)
        self.assertEqual(self.client.post(url, {"voucher_ids": [ids[1]]}, format="json").status_code, 403)
        self.vouchers[0].delete()
        self.assertEqual(VoucherPrintAuthorization.objects.count(), 1)

    def test_cross_tenant_print_ids_and_expiry_are_denied(self):
        other = Tenant.objects.create(name="Other", slug="other")
        self.vouchers[0].tenant = other
        self.vouchers[0].save()
        self.assertEqual(self.client.post("/api/v1/vouchers/authorize-print/", {"voucher_ids": [self.vouchers[0].pk]}, format="json").status_code, 400)
        self.sub.status = "expired"
        self.sub.save()
        self.assertEqual(self.client.post("/api/v1/vouchers/authorize-print/", {"voucher_ids": [self.vouchers[1].pk]}, format="json").status_code, 403)

    def test_print_day_uses_lagos_and_resets_quota(self):
        with patch("apps.subscriptions.entitlements.timezone.now", return_value=datetime(2026, 9, 7, 22, 59, tzinfo=dt_timezone.utc)):
            self.assertEqual(str(print_day()), "2026-09-07")
        first = print_day()
        authorize_print(self.tenant, [self.vouchers[0].pk])
        with patch("apps.subscriptions.entitlements.print_day", return_value=first+timedelta(days=1)):
            self.assertEqual(authorize_print(self.tenant, [self.vouchers[1].pk])["used"], 1)

    def test_whatsapp_disabled_blocks_create_and_runtime_but_allows_disable(self):
        response = self.client.post(reverse("whatsapp-route-list"), {"phone_number_id": "123456", "access_token_encrypted": "secret"}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        route = TenantWhatsAppRoute.objects.create(tenant=self.tenant, phone_number_id="123456", webhook_token="test-token", access_token_encrypted="secret")
        self.assertIsNone(generate_route_url(self.tenant))
        with self.assertRaises(PermissionDenied):
            route.generate_route_token()
        self.assertEqual(self.client.patch(reverse("whatsapp-route-detail", args=[route.pk]), {"is_active": False}, format="json").status_code, 200)

    def test_zero_unlimited_and_invalid_plan_limits(self):
        self.client.force_authenticate(self.admin)
        url = reverse("business-plan-detail", args=[self.plan.pk])
        for field in ("max_routers", "daily_voucher_print_limit"):
            self.assertEqual(self.client.patch(url, {"expected_version": 1, field: -1}, format="json").status_code, 400)
        self.client.force_authenticate(self.owner)
        period = SubscriptionPeriod.objects.get(tenant=self.tenant)
        period.terms = {**period.terms, "max_routers": 0, "daily_voucher_print_limit": 0}
        period.save()
        self.assertEqual(self.client.post("/api/v1/routers/", {"name": "Denied", "ip_address": "10.0.0.9", "nas_secret": "test-secret"}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            authorize_print(self.tenant, [self.vouchers[0].pk])
        period.terms = {**period.terms, "max_routers": None, "daily_voucher_print_limit": None}
        period.save()
        self.assertEqual(authorize_print(self.tenant, [item.pk for item in self.vouchers])["used"], 3)

    def test_whatsapp_token_respects_current_period_and_expiry(self):
        period = SubscriptionPeriod.objects.get(tenant=self.tenant)
        period.terms = {**period.terms, "whatsapp_enabled": True}
        period.save()
        route = TenantWhatsAppRoute.objects.create(tenant=self.tenant, phone_number_id="123456", webhook_token="test-token", access_token_encrypted="secret")
        token = route.generate_route_token()
        self.assertEqual(TenantWhatsAppRoute.resolve_route_token(token), self.tenant)
        self.sub.status = "expired"
        self.sub.save()
        self.assertIsNone(TenantWhatsAppRoute.resolve_route_token(token))

    def test_staff_print_grant_and_usage_response(self):
        from apps.accounts.staff_models import StaffAssignment
        staff = get_user_model().objects.create_user(username="staff", email="staff@test.com")
        StaffAssignment.objects.create(user=staff, tenant=self.tenant, services=["vouchers.print"], is_active=True)
        self.client.force_authenticate(staff)
        response = self.client.post("/api/v1/vouchers/authorize-print/", {"voucher_ids": [self.vouchers[0].pk]}, format="json", HTTP_X_TENANT_ID=str(self.tenant.pk))
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.owner)
        entitlements = self.client.get(reverse("tenant-subscription")).data["entitlements"]
        self.assertEqual(entitlements["vouchers_prepared_today"], 1)
        self.assertEqual(entitlements["terms"]["max_routers"], 1)
        self.assertEqual(entitlements["timezone"], "Africa/Lagos")

    def test_cancelled_periods_do_not_override_a_new_purchase_later(self):
        future = SubscriptionPayment.objects.create(tenant=self.tenant, plan=self.plan, reference="future-cancelled", amount=100000, plan_terms={**snapshot_plan(self.plan), "max_routers": 4})
        SubscriptionService.complete_payment(future)
        self.sub.refresh_from_db()
        self.sub.status = "cancelled"
        self.sub.save()
        replacement = SubscriptionPayment.objects.create(tenant=self.tenant, plan=self.plan, reference="replacement", amount=100000, plan_terms={**snapshot_plan(self.plan), "max_routers": 2, "duration_days": 90})
        SubscriptionService.complete_payment(replacement)
        future.period.refresh_from_db()
        self.assertTrue(future.period.superseded)
        with patch("apps.subscriptions.entitlements.timezone.now", return_value=future.period.starts_at + timedelta(seconds=1)):
            self.assertEqual(entitlement_terms(self.tenant)["max_routers"], 2)

    def test_legacy_without_subscription_keeps_access(self):
        other = Tenant.objects.create(name="Legacy", slug="legacy")
        self.assertIsNone(entitlement_terms(other)["max_routers"])
        self.assertTrue(entitlement_terms(other)["whatsapp_enabled"])


class ConcurrentLimitTests(Fixtures, TransactionTestCase):
    def setUp(self):
        self.setup_records()

    def test_two_batches_cannot_take_the_same_last_slot(self):
        barrier = Barrier(2)
        def run(pk):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                authorize_print(Tenant.objects.get(pk=self.tenant.pk), [pk])
                return True
            except PermissionDenied:
                return False
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(run, [v.pk for v in self.vouchers[:2]]))
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(VoucherPrintAuthorization.objects.count(), 1)

    def test_two_router_requests_cannot_exceed_cap(self):
        barrier = Barrier(2)
        def run(number):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(get_user_model().objects.get(pk=self.owner.pk))
                barrier.wait(timeout=10)
                return client.post("/api/v1/routers/", {"name": f"Router {number}", "ip_address": f"10.0.0.{number}", "nas_secret": "test-secret"}, format="json").status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(run, [1, 2]))
        self.assertEqual(sorted(outcomes), [201, 403])
        self.assertEqual(NASDevice.objects.filter(tenant=self.tenant).count(), 1)
