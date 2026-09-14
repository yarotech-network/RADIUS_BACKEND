from django.db import DatabaseError, transaction
from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import Replace, Upper
from apps.routers.selectors import tenant_radius_addresses
from apps.vouchers.models import Radacct


def device_accounting(devices, tenant):
    """Observe MAC usernames only on uniquely tenant-owned, assigned NAS addresses."""
    allowed = tenant_radius_addresses(tenant)
    targets = {}
    for device in devices:
        if device.router_id and device.router.tenant_id == tenant.pk:
            for ip in (device.router.ip_address, device.router.wireguard_ip):
                if ip and str(ip) in allowed:
                    targets[(device.mac_address.replace(":", ""), str(ip))] = device.pk
    result = {device.pk: {"available": True, "session_count": 0, "open_sessions": 0,
                         "bytes_total": None, "last_connected_at": None} for device in devices}
    if not targets:
        return result
    mac = Upper(Replace(Replace(Replace("username", Value(":"), Value("")), Value("-"), Value("")), Value("."), Value("")))
    try:
        # A missing accounting installation must not break registration CRUD. The savepoint
        # also keeps the surrounding request transaction usable after a database error.
        with transaction.atomic():
            rows = list(Radacct.objects.annotate(mac_key=mac).filter(
                mac_key__in={key[0] for key in targets}, nasipaddress__in={key[1] for key in targets},
                acctstarttime__isnull=False,
            ).values("mac_key", "nasipaddress").annotate(
                session_count=Count("radacctid"), open_sessions=Count("radacctid", filter=Q(acctstoptime__isnull=True)),
                bytes_in=Sum("acctinputoctets"), bytes_out=Sum("acctoutputoctets"), last_connected_at=Max("acctstarttime"),
            ))
    except DatabaseError:
        return {device.pk: {"available": False, "session_count": None, "open_sessions": None,
                            "bytes_total": None, "last_connected_at": None} for device in devices}
    for row in rows:
        device_id = targets.get((row["mac_key"], str(row["nasipaddress"])))
        if device_id is None:
            continue
        item = result[device_id]
        item["session_count"] += row["session_count"]
        item["open_sessions"] += row["open_sessions"]
        item["bytes_total"] = (item["bytes_total"] or 0) + (row["bytes_in"] or 0) + (row["bytes_out"] or 0)
        if item["last_connected_at"] is None or row["last_connected_at"] > item["last_connected_at"]:
            item["last_connected_at"] = row["last_connected_at"]
    return result
