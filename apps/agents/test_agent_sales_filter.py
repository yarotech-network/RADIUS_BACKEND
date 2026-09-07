from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from apps.vouchers.models import InternetPlan, Voucher
from .models import AgentProfile


class AgentSalesFilterTests(APITestCase):
    def test_exact_agent_filter_and_pagination_remain_tenant_scoped(self):
        tenant = Tenant.objects.create(name="Sales", slug="sales-filter")
        owner = get_user_model().objects.create_user(username="owner", email="owner@filter.test")
        TenantMembership.objects.create(user=owner, tenant=tenant, role="owner")
        plan = InternetPlan.objects.create(tenant=tenant, name="Daily", price=100, duration_hours=24)
        agent_user = get_user_model().objects.create_user(username="reseller", email="reseller@filter.test")
        agent = AgentProfile.objects.create(tenant=tenant, user=agent_user, status="active")
        wanted = Voucher.objects.create(tenant=tenant, agent=agent, plan=plan, username="EXACT001", password="test")
        Voucher.objects.create(tenant=tenant, plan=plan, username="reseller-unrelated", password="test")
        self.client.force_authenticate(owner)
        response = self.client.get("/api/v1/vouchers/", {"agent": agent.pk})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual([item["id"] for item in response.data["results"]], [wanted.pk])
        other = Tenant.objects.create(name="Other", slug="other-sales-filter")
        membership = owner.membership
        membership.tenant = other
        membership.save()
        self.client.force_authenticate(get_user_model().objects.get(pk=owner.pk))
        response = self.client.get("/api/v1/vouchers/", {"agent": agent.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
