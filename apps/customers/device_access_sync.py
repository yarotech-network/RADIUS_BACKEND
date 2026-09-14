import hashlib
import re
from datetime import timedelta, timezone as dt_timezone
from django.db import connection, transaction
from django.utils import timezone
from apps.routers.models import NASDevice
from apps.vouchers.models import Radacct, Voucher
from .models import DeviceAccessSession, DeviceAccessSync


def canonical_mac(value):
    value = re.sub(r"[:.\-]", "", (value or "").strip()).upper()
    if not re.fullmatch(r"[0-9A-F]{12}", value) or value == "000000000000":
        return None
    return ":".join(value[i:i + 2] for i in range(0, 12, 2))


def aware(value):
    # The legacy local accounting schema uses timestamp without timezone (UTC).
    return timezone.make_aware(value, dt_timezone.utc) if timezone.is_naive(value) else value


@transaction.atomic
def sync_device_access():
    DeviceAccessSync.objects.get_or_create(pk=1)
    state = DeviceAccessSync.objects.select_for_update().get(pk=1)
    with connection.cursor() as cursor:
        columns = {c.name for c in connection.introspection.get_table_description(cursor, "radacct")}
    if "callingstationid" not in columns:
        raise ValueError("Accounting schema needs callingstationid; apply the customer device-access migration.")
    # Reject addresses shared by routers/tenants; both voucher AND NAS must match.
    addresses = {}
    for router in NASDevice.objects.all():
        for address in {str(ip) for ip in (router.ip_address, router.wireguard_ip) if ip}:
            addresses.setdefault(address, []).append(router)
    vouchers = {v.username: v for v in Voucher.objects.only("id", "username", "tenant_id")}
    missing = imported = 0
    now = timezone.now()
    for row in Radacct.objects.filter(acctstarttime__isnull=False).iterator(chunk_size=1000):
        voucher = vouchers.get(row.username)
        routers = addresses.get(str(row.nasipaddress), [])
        if not voucher or len(routers) != 1 or routers[0].tenant_id != voucher.tenant_id:
            continue
        mac = canonical_mac(row.callingstationid)
        if not mac:
            missing += 1
            continue
        start = aware(row.acctstarttime)
        stop = aware(row.acctstoptime) if row.acctstoptime else None
        if start > now or (stop and stop < start):
            continue
        seen = min(now, max(start, stop or start + timedelta(seconds=max(0, row.acctsessiontime or 0))))
        key = hashlib.sha256(f"{voucher.pk}|{row.nasipaddress}|{row.sessionid}|{start.isoformat()}".encode()).hexdigest()
        defaults = dict(tenant_id=voucher.tenant_id, voucher_id=voucher.pk, mac_address=mac,
            router_name=routers[0].name, nas_address=row.nasipaddress, started_at=start,
            last_seen_at=seen, stopped_at=stop, bytes_in=max(0, row.acctinputoctets or 0),
            bytes_out=max(0, row.acctoutputoctets or 0))
        existing = DeviceAccessSession.objects.filter(source_key=key).first()
        if existing and (existing.mac_address != mac or existing.tenant_id != voucher.tenant_id):
            continue  # Never reassign an existing session to a different identity.
        if existing:
            # A repeated or older accounting delivery must not regress evidence.
            defaults["last_seen_at"] = max(existing.last_seen_at, seen)
            defaults["stopped_at"] = stop or existing.stopped_at
            defaults["bytes_in"] = max(existing.bytes_in, defaults["bytes_in"])
            defaults["bytes_out"] = max(existing.bytes_out, defaults["bytes_out"])
        DeviceAccessSession.objects.update_or_create(source_key=key, defaults=defaults)
        imported += 1
    state.completed_at = now
    state.missing_mac_rows = missing
    state.save()
    return imported, missing
