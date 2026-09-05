from unittest.mock import patch

from django.db.utils import OperationalError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator


class OpenApiContractTests(SimpleTestCase):
    def test_new_command_and_pagination_schemas_match_wire_contract(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        schemas = schema["components"]["schemas"]
        self.assertIn("current_password", schemas["ReplaceSecrets"]["required"])
        self.assertIn("expected_updated_at", schemas["ReplaceSecrets"]["required"])
        self.assertIn("action", schemas["Provision"]["required"])
        operation = schema["paths"]["/api/v1/routers/{id}/provisioning/"]["post"]
        self.assertIn("202", operation["responses"])
        self.assertIn("Idempotency-Key", [parameter["name"] for parameter in operation.get("parameters", [])])
        for name, component in schemas.items():
            if name.startswith("Paginated"):
                self.assertIn("total_pages", component["properties"], name)
                self.assertNotIn("next", component["properties"], name)

    def test_schema_contains_critical_public_and_authenticated_routes(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)

        expected_paths = {
            "/api/v1/auth/login/",
            "/api/v1/auth/register/",
            "/api/v1/tenants/",
            "/api/v1/vouchers/",
            "/api/v1/agent/wallet/fund/",
            "/api/v1/buy/",
            "/api/v1/internal/router-provisioning/",
            "/api/v1/iot-devices/",
            "/api/v1/dashboard/stats/",
            "/api/v1/dashboard/live-users/{session_id}/disconnect/",
            "/api/v1/subscriptions/checkout/",
        }

        self.assertTrue(expected_paths.issubset(schema["paths"]))

    def test_operation_ids_are_unique(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        operation_ids = [
            operation["operationId"]
            for path_item in schema["paths"].values()
            for method, operation in path_item.items()
            if method in {"get", "post", "put", "patch", "delete"}
        ]

        self.assertEqual(len(operation_ids), len(set(operation_ids)))


class LivenessTests(SimpleTestCase):
    def test_liveness_reports_ok_without_database_access(self):
        response = self.client.get(reverse("health-live"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "max-age=0, no-cache, no-store, must-revalidate, private")

    def test_liveness_rejects_non_get_methods(self):
        self.assertEqual(self.client.post(reverse("health-live")).status_code, 405)


class ReadinessTests(TestCase):
    def test_readiness_reports_ok_when_database_is_available(self):
        response = self.client.get(reverse("health-ready"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @patch("apps.core.health.connection.cursor", side_effect=OperationalError)
    def test_readiness_reports_unavailable_without_leaking_error_details(self, _cursor):
        response = self.client.get(reverse("health-ready"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    @patch("apps.core.health.cache.set", side_effect=OSError("redis unavailable"))
    def test_readiness_reports_unavailable_when_shared_cache_is_down(self, _cache_set):
        response = self.client.get(reverse("health-ready"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
