from unittest.mock import patch
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.routers.models import NASDevice, RouterAuditEvent
from apps.routers.radius_client import RadiusUnavailable
from apps.vouchers.models import Radacct
from apps.tenants.models import Tenant, TenantMembership
from apps.vouchers.models import InternetPlan, PaymentTransaction, Voucher

User = get_user_model()

class DashboardTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="A", slug="a")
        other = Tenant.objects.create(name="B", slug="b")
        self.user = User.objects.create_user(username="owner", email="owner@example.com", password="StrongPass-4821")
        TenantMembership.objects.create(user=self.user, tenant=self.tenant, role="owner")
        plan = InternetPlan.objects.create(tenant=self.tenant, name="A", price=1000, duration_hours=24, rate_limit="1M/1M")
        other_plan = InternetPlan.objects.create(tenant=other, name="B", price=1000, duration_hours=24, rate_limit="1M/1M")
        Voucher.objects.create(username="own", password="x", tenant=self.tenant, plan=plan, status="active")
        Voucher.objects.create(username="other", password="x", tenant=other, plan=other_plan, status="active")
        PaymentTransaction.objects.create(reference="own", amount=1000, status="success", customer_email="a@example.com", tenant=self.tenant, plan=plan)
        PaymentTransaction.objects.create(reference="other", amount=9000, status="success", customer_email="b@example.com", tenant=other, plan=other_plan)
        self.router = NASDevice.objects.create(tenant=self.tenant, name="Router", ip_address="10.0.0.1", nas_secret="x", onboarding_state="active")

    def test_stats_are_authenticated_and_tenant_scoped(self):
        self.assertEqual(self.client.get(reverse("dashboard-stats")).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("dashboard-stats"))
        self.assertEqual(response.data["total_vouchers"], 1)
        self.assertEqual(response.data["total_revenue"], 1000)
        self.assertEqual(response.data["active_routers"], 1)

    @patch("apps.vouchers.models.Radacct.objects.filter")
    def test_live_users_filters_active_sessions_by_tenant_router_ips(self, sessions):
        self.router.wireguard_ip = "10.100.100.2"
        self.router.save(update_fields=["wireguard_ip"])
        sessions.return_value = [SimpleNamespace(
            radacctid=42,
            username="own",
            nasipaddress="10.0.0.1",
            acctsessiontime=120,
            acctinputoctets=1000,
            acctoutputoctets=2000,
            acctstarttime=None,
        )]
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("live-users"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kwargs = sessions.call_args.kwargs
        self.assertIn("nasipaddress__in", kwargs)
        self.assertEqual(
            kwargs["nasipaddress__in"], {"10.0.0.1", "10.100.100.2"}
        )
        self.assertTrue(kwargs["acctstoptime__isnull"])
        self.assertEqual(response.data["users"][0]["session_id"], 42)
        self.assertIsNone(response.data["users"][0]["client_ip"])

    @patch("apps.vouchers.services.RadiusService.disconnect_session", return_value=True)
    @patch("apps.vouchers.models.Radacct.objects.get")
    def test_manager_disconnects_only_tenant_session_and_records_ack(self, get_session, disconnect):
        get_session.return_value = SimpleNamespace(
            radacctid=42,
            sessionid="radius-session-42",
            nasipaddress="10.0.0.1",
            nasportid="ether2",
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse("disconnect-session", args=[42]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"acknowledged": True})
        self.assertIn("nasipaddress__in", get_session.call_args.kwargs)
        disconnect.assert_called_once_with(
            session_id="radius-session-42",
            nas_ip="10.0.0.1",
            nas_port="ether2",
            callingsession_id="",
            shared_secret="x",
        )
        event = RouterAuditEvent.objects.get(action="radius_disconnect_request")
        self.assertEqual(event.details, {"radacct_id": 42, "acknowledged": True})

    @patch("apps.vouchers.models.Radacct.objects.get", side_effect=Radacct.DoesNotExist)
    def test_unknown_or_cross_tenant_session_is_hidden(self, get_session):
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse("disconnect-session", args=[999]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(
        "apps.vouchers.services.RadiusService.disconnect_session",
        side_effect=RadiusUnavailable("timeout"),
    )
    @patch("apps.vouchers.models.Radacct.objects.get")
    def test_disconnect_outage_returns_safe_retryable_failure(self, get_session, disconnect):
        get_session.return_value = SimpleNamespace(
            radacctid=42,
            sessionid="radius-session-42",
            nasipaddress="10.0.0.1",
            nasportid="ether2",
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse("disconnect-session", args=[42]))

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertNotIn("timeout", str(response.data))
        self.assertFalse(RouterAuditEvent.objects.exists())
