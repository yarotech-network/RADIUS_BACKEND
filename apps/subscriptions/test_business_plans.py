from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from .models import SubscriptionPlan


class BusinessPlanTests(APITestCase):
    def setUp(self):
        user = get_user_model()
        self.admin = user.objects.create_user(username="admin", email="admin@test.com", is_platform_admin=True)
        self.member = user.objects.create_user(username="member", email="member@test.com")
        self.url = reverse("business-plan-list")
        self.payload = {"name": "Business", "price": 500050, "duration_days": 90, "features": ["Voucher management", "Router management"]}

    def test_admin_publishes_plan_and_duplicate_request_replays(self):
        self.client.force_authenticate(self.admin)
        first = self.client.post(self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="business-plan-test-1234")
        self.assertEqual(first.status_code, 201, first.data)
        replay = self.client.post(self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="business-plan-test-1234")
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(SubscriptionPlan.objects.count(), 1)
        self.assertEqual(self.client.get(self.url).data["count"], 1)
        self.client.force_authenticate(None)
        public = self.client.get(reverse("subscription-plan-list"))
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data["results"][0]["price"], 500050)
        self.assertEqual(public.data["results"][0]["features"], self.payload["features"])

    def test_anonymous_and_non_admin_cannot_manage_plans(self):
        for user in (None, self.member):
            self.client.force_authenticate(user)
            self.assertIn(self.client.get(self.url).status_code, (401, 403))
            self.assertIn(self.client.post(self.url, self.payload, format="json").status_code, (401, 403))
        self.assertFalse(SubscriptionPlan.objects.exists())

    def test_invalid_prices_duration_and_features_are_rejected(self):
        self.client.force_authenticate(self.admin)
        for change in ({"price": -1}, {"price": 0}, {"duration_days": 0}, {"duration_days": 1.5}, {"features": {"x": True}}, {"features": ["x" * 301]}, {"name": " "}):
            response = self.client.post(self.url, {**self.payload, **change}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(SubscriptionPlan.objects.exists())
