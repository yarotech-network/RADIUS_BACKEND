import subprocess
from django.utils import timezone
from .models import NASDevice
from .secret_store import secret_store


class RouterService:
    """Router management services."""

    @staticmethod
    def ping_router(ip_address):
        """Ping router to check reachability."""
        result = subprocess.run(
            ["ping", "-n", "3", ip_address],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0

    @staticmethod
    def refresh_router_status(router):
        """Check if router is online and update last_seen_at."""
        is_online = RouterService.ping_router(router.ip_address)
        if is_online:
            router.last_seen_at = timezone.now()
            router.save(update_fields=["last_seen_at"])
        return is_online

    @staticmethod
    def refresh_all_statuses(tenant=None):
        """Refresh status for all routers."""
        query = NASDevice.objects.filter(is_active=True)
        if tenant:
            query = query.filter(tenant=tenant)

        results = []
        for router in query:
            is_online = RouterService.refresh_router_status(router)
            results.append({
                "router_id": str(router.id),
                "name": router.name,
                "online": is_online,
            })
        return results

    @staticmethod
    def register_nas_client(router):
        """Register router in FreeRADIUS nas table."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO nas (nasname, shortname, secret, type, ports, host_descriptor)
                VALUES (%s, %s, %s, 'other', 0, 'radius')
                ON CONFLICT (nasname) DO UPDATE SET secret = EXCLUDED.secret
                """,
                [router.radius_ip, router.name, secret_store.decrypt(router.nas_secret)],
            )
        return True
