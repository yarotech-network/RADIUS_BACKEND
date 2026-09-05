"""API boundary tests using the isolated PostgreSQL database and fake providers."""
from datetime import timedelta
from unittest.mock import patch
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from apps.tenants.models import Tenant, TenantMembership
from apps.accounts.staff_models import StaffAssignment, StaffInvitation
from apps.agents.models import AgentProfile, AgentWallet
from apps.routers.models import NASDevice, RouterOperation
from apps.routers.operations import run_one_router_operation
from apps.routers.secret_store import secret_store
from apps.vouchers.models import InternetPlan, PaymentTransaction, Voucher
from apps.payments.models import PaymentDelivery
from apps.payments.delivery import run_one_delivery
from apps.core.models import ApiCommand, AuditEvent

User = get_user_model()


class ApiWorkflowTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Alpha", slug="alpha")
        self.other = Tenant.objects.create(name="Beta", slug="beta")
        self.owner = User.objects.create_user("owner", "owner@example.com", "Strong-Password-2819")
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role="owner")
        self.admin = User.objects.create_user("admin", "admin@example.com", "Strong-Password-2819", is_platform_admin=True)
        self.staff = User.objects.create_user("staff", "staff@example.com", "Strong-Password-2819")
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name="Daily", price=5000, duration_hours=24, rate_limit="1M/1M")
        self.router = NASDevice.objects.create(tenant=self.tenant, name="Router", ip_address="192.0.2.1", nas_secret=secret_store.encrypt("original-secret"), wireguard_ip="10.100.100.2", wireguard_public_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
        self.payment = PaymentTransaction.objects.create(tenant=self.tenant, plan=self.plan, reference="original-payment", amount=5000, customer_email="buyer@example.com")
        self.client.force_authenticate(self.owner)

    def post(self, path, data=None, key=None):
        headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
        return self.client.post("/api/v1/" + path, data or {}, format="json", **headers)

    def agent_payload(self):
        return {"username": "newagent", "email": "newagent@example.com", "password": "Strong-Agent-2918!", "phone": "08012345678", "shop_name": "Shop", "commission_rate": "12.50"}

    def test_agent_creation_replay_does_not_duplicate_wallet_or_audit(self):
        payload = self.agent_payload()
        first = self.post("tenant/agents/", payload, "agent-create-0001")
        self.assertEqual(first.status_code, 201, first.data)
        second = self.post("tenant/agents/", payload, "agent-create-0001")
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second["Idempotency-Replayed"], "true")
        self.assertEqual(first.data, second.data)
        self.assertEqual(AgentProfile.objects.count(), 1)
        self.assertEqual(AgentWallet.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="agent.created").count(), 1)
        self.assertNotIn(payload["password"], str(first.data))
        self.assertNotIn(payload["password"], str(ApiCommand.objects.get().response))
        payload["phone"] = "08011111111"
        self.assertEqual(self.post("tenant/agents/", payload, "agent-create-0001").status_code, 409)

    def test_agent_approval_suspension_and_cross_tenant_hiding(self):
        response = self.post("tenant/agents/", self.agent_payload())
        agent = AgentProfile.objects.get()
        self.assertEqual(agent.status, "pending")
        self.assertEqual(self.post(f"tenant/agents/{agent.pk}/approve/").status_code, 200)
        agent.refresh_from_db()
        self.assertEqual(agent.status, "active")
        self.assertEqual(self.post(f"tenant/agents/{agent.pk}/suspend/").status_code, 200)
        agent.refresh_from_db()
        self.assertEqual(agent.status, "suspended")
        agent.tenant = self.other
        agent.save()
        self.assertEqual(self.post(f"tenant/agents/{agent.pk}/approve/").status_code, 404)

    def test_agent_invalid_commission_and_weak_password_leave_no_account(self):
        for changes in ({"commission_rate": "101"}, {"password": "password"}):
            self.assertEqual(self.post("tenant/agents/", {**self.agent_payload(), **changes}).status_code, 400)
        self.assertFalse(User.objects.filter(username="newagent").exists())

    def test_public_catalogue_is_paginated_and_hides_inactive_resources(self):
        self.client.force_authenticate(None)
        InternetPlan.objects.create(tenant=self.tenant, name="Hidden", price=1, duration_hours=1, rate_limit="1M/1M", is_active=False)
        response = self.client.get("/api/v1/public/tenants/alpha/plans/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.plan.pk)
        self.tenant.is_active = False
        self.tenant.save()
        self.assertEqual(self.client.get("/api/v1/public/tenants/alpha/").status_code, 404)

    def test_assignment_requires_explicit_tenant_and_each_service_grant(self):
        assignment = StaffAssignment.objects.create(user=self.staff, tenant=self.tenant, services=["routers.view"])
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/v1/routers/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/routers/", HTTP_X_TENANT_ID=str(self.tenant.pk)).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/routers/", HTTP_X_TENANT_ID=str(self.other.pk)).status_code, 403)
        response = self.client.post(f"/api/v1/routers/{self.router.pk}/provisioning/", {"action": "provision"}, HTTP_X_TENANT_ID=str(self.tenant.pk))
        self.assertEqual(response.status_code, 403)
        assignment.is_active = False
        assignment.save()
        self.assertEqual(self.client.get("/api/v1/routers/", HTTP_X_TENANT_ID=str(self.tenant.pk)).status_code, 403)

    def test_new_staff_invitation_creates_account_once_without_exposing_digest(self):
        self.client.force_authenticate(self.admin)
        created = self.post("platform/staff-invitations/", {"email": "invited@example.com", "tenant": self.tenant.pk, "services": ["routers.view"]})
        self.assertEqual(created.status_code, 201, created.data)
        token = created.data["token"]
        invitation = StaffInvitation.objects.get()
        self.assertNotEqual(invitation.token_digest, token)
        self.assertNotIn("token", self.client.get("/api/v1/platform/staff-invitations/").data["results"][0])
        self.client.force_authenticate(None)
        payload = {"token": token, "username": "invited", "password": "Strong-Invite-1284!"}
        accepted = self.post("staff-invitations/accept/", payload)
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertTrue(User.objects.get(username="invited").check_password(payload["password"]))
        self.assertEqual(self.post("staff-invitations/accept/", payload).status_code, 400)
        self.assertEqual(StaffAssignment.objects.count(), 1)

    def test_expired_invite_cannot_create_an_account(self):
        self.client.force_authenticate(self.admin)
        created = self.post("platform/staff-invitations/", {"email": "invited@example.com", "tenant": self.tenant.pk, "services": ["routers.view"]})
        StaffInvitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.client.force_authenticate(None)
        result = self.post("staff-invitations/accept/", {"token": created.data["token"], "username": "invited", "password": "Strong-Invite-1284!"})
        self.assertEqual(result.status_code, 400)
        self.assertFalse(User.objects.filter(username="invited").exists())

    @patch("apps.routers.operations.WireGuardManager")
    def test_provisioning_is_durable_blocks_edits_and_records_outcome(self, manager):
        response = self.post(f"routers/{self.router.pk}/provisioning/", {"action": "provision"}, "router-command-0001")
        self.assertEqual(response.status_code, 202, response.data)
        manager.assert_not_called()
        self.assertEqual(self.client.patch(f"/api/v1/routers/{self.router.pk}/", {"name": "Race"}).status_code, 409)
        self.assertEqual(self.post(f"routers/{self.router.pk}/provisioning/", {"action": "suspend"}).status_code, 409)
        self.assertTrue(run_one_router_operation())
        manager.return_value.create_peer.assert_called_once()
        self.assertFalse(run_one_router_operation())
        operation = RouterOperation.objects.get()
        self.assertEqual(operation.status, "succeeded")
        self.router.refresh_from_db()
        self.assertEqual(self.router.deployment_status, "deployed")
        self.assertEqual(self.client.get(f"/api/v1/router-operations/{operation.pk}/").status_code, 200)

    @patch("apps.routers.operations.WireGuardManager", side_effect=OSError("secret-server-address"))
    def test_provisioning_failure_is_visible_without_infrastructure_details(self, manager):
        self.post(f"routers/{self.router.pk}/provisioning/", {"action": "provision"})
        run_one_router_operation()
        operation = RouterOperation.objects.get()
        self.assertEqual(operation.status, "failed")
        self.assertEqual(operation.error_code, "provisioning_failed")
        self.assertNotIn("secret-server", str(self.client.get(f"/api/v1/router-operations/{operation.pk}/").data))

    def test_secret_replacement_requires_password_and_current_version(self):
        path = f"routers/{self.router.pk}/replace-secrets/"
        payload = {"current_password": "wrong", "nas_secret": "z" * 255, "expected_updated_at": self.router.updated_at.isoformat()}
        self.assertEqual(self.post(path, payload).status_code, 400)
        payload["current_password"] = "Strong-Password-2819"
        response = self.post(path, payload)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("nas_secret", response.data)
        self.router.refresh_from_db()
        self.assertEqual(secret_store.decrypt(self.router.nas_secret), "z" * 255)
        self.assertGreater(len(self.router.nas_secret), 255)
        self.assertEqual(self.post(path, payload).status_code, 409)
        self.assertNotIn("z" * 255, str(list(AuditEvent.objects.values())))

    def test_health_never_invents_online_or_cpu_information(self):
        result = self.client.get(f"/api/v1/routers/{self.router.pk}/health/")
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.data["online"])
        self.assertFalse(result.data["telemetry_available"])
        self.assertNotIn("cpu_load", result.data)

    @patch("apps.vouchers.services.Radcheck.objects.create")
    @patch("apps.payments.recovery_api.get_paystack_service")
    def test_recovery_verifies_original_payment_and_issues_only_one_voucher(self, service, radius):
        service.return_value.verify_transaction.return_value = {"data": {"reference": self.payment.reference, "status": "success", "amount": 5000, "currency": "NGN"}}
        path = f"payment-recovery/{self.payment.pk}/retry/"
        self.assertEqual(self.post(path).status_code, 200)
        self.assertEqual(self.post(path).status_code, 200)
        self.assertEqual(Voucher.objects.count(), 1)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "success")
        self.assertIsNotNone(self.payment.verified_at)
        service.return_value.initialize_transaction.assert_not_called()
        service.return_value.verify_transaction.assert_called_with("original-payment")

    @patch("apps.payments.recovery_api.get_paystack_service")
    def test_wrong_amount_never_fulfills_payment(self, service):
        service.return_value.verify_transaction.return_value = {"data": {"reference": self.payment.reference, "status": "success", "amount": 1, "currency": "NGN"}}
        self.assertEqual(self.post(f"payment-recovery/{self.payment.pk}/retry/").status_code, 409)
        self.assertFalse(Voucher.objects.exists())
        self.payment.refresh_from_db()
        self.assertIsNone(self.payment.verified_at)

    @patch("apps.payments.delivery.send_mail", side_effect=TimeoutError("smtp credentials"))
    def test_uncertain_delivery_is_not_automatically_repeated(self, send):
        voucher = Voucher.objects.create(tenant=self.tenant, plan=self.plan, username="voucher", password="private")
        self.payment.voucher = voucher
        self.payment.status = "success"
        self.payment.save()
        path = f"payment-recovery/{self.payment.pk}/deliver/"
        self.assertEqual(self.post(path).status_code, 202)
        self.assertTrue(run_one_delivery())
        self.assertFalse(run_one_delivery())
        self.assertEqual(PaymentDelivery.objects.get().status, "unknown")
        self.assertEqual(self.post(path).status_code, 409)
        self.assertEqual(self.post(path, {"acknowledge_duplicate_risk": True}).status_code, 202)
        send.assert_called_once()

    def test_platform_endpoints_reject_tenant_owner_and_hide_router_secrets(self):
        for path in ("platform/dashboard/", "platform/routers/", "platform/payments/", "platform/audit-events/"):
            self.assertEqual(self.client.get("/api/v1/" + path).status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/v1/platform/dashboard/").data["routers"], 1)
        router = self.client.get("/api/v1/platform/routers/").data["results"][0]
        self.assertNotIn("nas_secret", router)
        self.assertNotIn("routeros_password_encrypted", router)

    def test_cross_tenant_recovery_and_audit_are_hidden(self):
        self.payment.tenant = self.other
        self.payment.save()
        self.assertEqual(self.post(f"payment-recovery/{self.payment.pk}/retry/").status_code, 404)
        AuditEvent.objects.create(tenant=self.other, actor=self.admin, action="private", resource="test")
        self.assertEqual(self.client.get("/api/v1/audit-events/").data["count"], 0)

    def test_errors_have_additive_problem_envelope(self):
        response = self.post("tenant/agents/", {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.json())
        self.assertEqual(response.json()["problem"]["code"], "http_400")
        self.assertEqual(self.client.get("/api/v1/no-such-route/").json()["problem"]["code"], "http_404")

    def test_logout_revokes_refresh_token_and_rejects_other_users_token(self):
        own = str(RefreshToken.for_user(self.owner))
        foreign = str(RefreshToken.for_user(self.staff))
        self.assertEqual(self.post("auth/logout/", {"refresh": foreign}).status_code, 403)
        self.assertEqual(self.post("auth/logout/", {"refresh": own}).status_code, 204)
        self.client.force_authenticate(None)
        self.assertEqual(self.post("auth/token/refresh/", {"refresh": own}).status_code, 401)

    def test_tenant_profile_cannot_change_identity_or_privileged_flags(self):
        result = self.client.patch("/api/v1/tenants/profile/", {"name": "Renamed", "slug": "stolen", "is_active": False, "is_platform_admin": True}, format="json")
        self.assertEqual(result.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, "Renamed")
        self.assertEqual(self.tenant.slug, "alpha")
        self.assertTrue(self.tenant.is_active)
        self.assertFalse(self.tenant.is_platform_admin)

    def test_final_tenant_owner_cannot_be_demoted_or_deleted(self):
        path = f"/api/v1/tenant-memberships/{self.owner.membership.pk}/"
        self.assertEqual(self.client.patch(path, {"role": "staff"}).status_code, 400)
        self.assertEqual(self.client.delete(path).status_code, 400)
        self.owner.membership.refresh_from_db()
        self.assertEqual(self.owner.membership.role, "owner")

    def test_inactive_tenant_blocks_private_api_and_public_purchase(self):
        self.tenant.is_active = False
        self.tenant.save()
        self.assertEqual(self.client.get("/api/v1/routers/").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.post("buy/", {"plan_id": self.plan.pk, "email": "buyer@example.com"}).status_code, 400)

    def test_secret_replacement_cannot_be_bypassed_by_regular_patch(self):
        result = self.client.patch(f"/api/v1/routers/{self.router.pk}/", {"nas_secret": "bypass"})
        self.assertEqual(result.status_code, 400)
        self.router.refresh_from_db()
        self.assertEqual(secret_store.decrypt(self.router.nas_secret), "original-secret")

    def test_long_whatsapp_token_round_trips_without_being_returned(self):
        response = self.post("whatsapp/routes/", {"phone_number_id": "12345", "access_token_encrypted": "t" * 500, "is_active": True})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("access_token_encrypted", response.data)
        self.assertEqual(secret_store.decrypt(self.tenant.whatsapp_route.access_token_encrypted), "t" * 500)

    def test_case_variant_agent_email_is_rejected(self):
        response = self.post("tenant/agents/", {**self.agent_payload(), "email": "OWNER@example.com"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AgentProfile.objects.exists())

    @patch("apps.payments.delivery.send_mail", return_value=1)
    def test_delivery_reports_acceptance_not_inbox_delivery(self, send):
        self.payment.voucher = Voucher.objects.create(tenant=self.tenant, plan=self.plan, username="accepted", password="private")
        self.payment.status = "success"
        self.payment.save()
        self.assertEqual(self.post(f"payment-recovery/{self.payment.pk}/deliver/").status_code, 202)
        self.assertTrue(run_one_delivery())
        self.assertEqual(PaymentDelivery.objects.get().status, "accepted")
        self.assertFalse(run_one_delivery())
        send.assert_called_once()

    @patch("apps.payments.recovery_api.get_paystack_service")
    @patch("apps.payments.recovery.VoucherService.generate_vouchers", side_effect=RuntimeError("private failure"))
    def test_failed_fulfillment_retains_verified_payment_evidence(self, generate, service):
        service.return_value.verify_transaction.return_value = {"data": {"reference": self.payment.reference, "status": "success", "amount": 5000, "currency": "NGN"}}
        result = self.post(f"payment-recovery/{self.payment.pk}/retry/")
        self.assertEqual(result.status_code, 503)
        self.payment.refresh_from_db()
        self.assertIsNotNone(self.payment.verified_at)
        self.assertIsNone(self.payment.voucher_id)
        detail = self.client.get(f"/api/v1/payment-recovery/{self.payment.pk}/")
        self.assertEqual(detail.data["fulfillment_status"], "paid_unfulfilled")

    def test_error_for_invalid_idempotency_key_precedes_mutation(self):
        self.assertEqual(self.post("tenant/agents/", self.agent_payload(), "short").status_code, 400)
        self.assertFalse(AgentProfile.objects.exists())
        self.assertFalse(ApiCommand.objects.exists())

    def test_public_plan_filter_and_page_limit(self):
        InternetPlan.objects.bulk_create([InternetPlan(tenant=self.tenant, name=f"Extra {i}", price=i, duration_hours=1, rate_limit="1M/1M") for i in range(105)])
        result = self.client.get("/api/v1/public/tenants/alpha/plans/?page_size=1000")
        self.assertEqual(len(result.data["results"]), 100)
        self.assertEqual(result.data["count"], 106)
        result = self.client.get("/api/v1/public/tenants/alpha/plans/?search=Daily")
        self.assertEqual(result.data["count"], 1)

    def test_ambiguous_router_addresses_are_excluded_from_tenant_sessions(self):
        from apps.routers.selectors import tenant_radius_addresses
        NASDevice.objects.create(tenant=self.other, name="Shared address", ip_address=self.router.ip_address, nas_secret="other")
        self.assertEqual(tenant_radius_addresses(self.tenant), {self.router.wireguard_ip})
        self.assertEqual(tenant_radius_addresses(self.other), set())

    def test_shared_address_within_tenant_does_not_misidentify_a_router(self):
        from apps.routers.selectors import tenant_radius_addresses
        NASDevice.objects.create(tenant=self.tenant, name="Another site", ip_address=self.router.ip_address, nas_secret="other")
        self.assertEqual(tenant_radius_addresses(self.tenant), {self.router.wireguard_ip})

    def test_platform_payment_views_are_separate_and_admin_only(self):
        for path in ("platform/wallet-payments/", "platform/subscription-payments/"):
            self.assertEqual(self.client.get("/api/v1/" + path).status_code, 403)
        self.client.force_authenticate(self.admin)
        for path in ("platform/wallet-payments/", "platform/subscription-payments/"):
            result = self.client.get("/api/v1/" + path)
            self.assertEqual(result.status_code, 200)
            self.assertIn("results", result.data)

    @patch("apps.routers.operations.WireGuardManager")
    def test_expired_worker_lease_can_recover_a_router_operation(self, manager):
        self.post(f"routers/{self.router.pk}/provisioning/", {"action": "provision"})
        RouterOperation.objects.update(status="running", attempts=1, lease_until=timezone.now() - timedelta(seconds=1))
        self.assertTrue(run_one_router_operation())
        operation = RouterOperation.objects.get()
        self.assertEqual(operation.attempts, 2)
        self.assertEqual(operation.status, "succeeded")

    @patch("apps.routers.operations.WireGuardManager")
    def test_stale_worker_cannot_overwrite_a_newer_claim(self, manager):
        self.post(f"routers/{self.router.pk}/provisioning/", {"action": "provision"})
        manager.return_value.create_peer.side_effect = lambda *args: RouterOperation.objects.update(attempts=2)
        run_one_router_operation()
        operation = RouterOperation.objects.get()
        self.assertEqual(operation.status, "running")
        self.assertEqual(operation.attempts, 2)
        self.router.refresh_from_db()
        self.assertEqual(self.router.deployment_status, "deploying")

    @override_settings(ROUTER_PROVISIONING_AGENT_KEYS=["test-key-for-provisioning"], ROUTER_PROVISIONING_AGENT_ALLOWED_NETWORKS=["127.0.0.1"])
    @patch("apps.routers.provisioning_views.WireGuardManager")
    def test_legacy_provisioning_cannot_race_with_queued_command(self, manager):
        import hashlib, hmac, json, time, uuid
        self.post(f"routers/{self.router.pk}/provisioning/", {"action": "provision"})
        body = json.dumps({"request_id": str(uuid.uuid4()), "action": "suspend_wireguard_peer", "router_id": str(self.router.pk)})
        timestamp = str(int(time.time()))
        signature = hmac.new(b"test-key-for-provisioning", f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
        result = self.client.post("/api/v1/internal/router-provisioning/", body, content_type="application/json", HTTP_X_PROVISIONING_TIMESTAMP=timestamp, HTTP_X_PROVISIONING_SIGNATURE=signature, HTTP_X_PROVISIONING_KEY_ID="test-key")
        self.assertEqual(result.status_code, 409, result.data)
        manager.assert_not_called()

    def test_non_object_command_bodies_return_validation_errors(self):
        result = self.client.post(f"/api/v1/routers/{self.router.pk}/transition/", [1], format="json")
        self.assertEqual(result.status_code, 400)
        AgentProfile.objects.create(user=self.staff, tenant=self.tenant, phone="08012345678", status="active")
        self.client.force_authenticate(self.staff)
        result = self.client.post("/api/v1/agent/vouchers/generate/", [1], format="json")
        self.assertEqual(result.status_code, 400)
