from django.core.cache import cache
from django.db import connection
from django.db.utils import DatabaseError
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def liveness(request):
    """Report that the Django process and URL routing are responsive."""
    return JsonResponse({"status": "ok"})


@require_GET
@never_cache
def readiness(request):
    """Report whether the essential database dependency accepts a query."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        cache.set("health:readiness", "ok", timeout=5)
        if cache.get("health:readiness") != "ok":
            raise RuntimeError("cache readiness probe failed")
        cache.delete("health:readiness")
    except Exception:
        # Cache backends expose backend-specific connection exceptions. Health
        # responses intentionally collapse all dependency failures to a safe 503.
        return JsonResponse({"status": "unavailable"}, status=503)

    return JsonResponse({"status": "ok"})
