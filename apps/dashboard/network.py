"""Accounting summaries; missing telemetry never implies confirmed offline."""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.routers.models import NASDevice
from apps.routers.selectors import tenant_radius_addresses
from apps.vouchers.models import Radacct, Voucher
from .metrics import boundaries

FRESH_SECONDS = 300


def fresh_condition(now):
    cutoff = now - timedelta(seconds=FRESH_SECONDS)
    return (Q(acctstoptime__isnull=True) &
            (Q(acctupdatetime__gte=cutoff, acctupdatetime__lte=now) |
             Q(acctupdatetime__isnull=True, acctstarttime__gte=cutoff, acctstarttime__lte=now)))


def sample_rates(tenant_id, rows, now):
    """Compare the same session's counters and accounting timestamps, not page totals.

    Bounded cache sample, no credentials. A lock prevents concurrent pollers from
    replacing each other's baseline. Counter resets/reconnects require a new sample.
    """
    empty = {'upload_bytes_per_second': None, 'download_bytes_per_second': None,
             'rate_sampled_sessions': 0}
    if len(rows) > 10000:
        return empty
    key = f'dashboard-hotspot-rate-v1:{tenant_id}'
    try:
        if not cache.add(key + ':lock', True, timeout=10):
            return empty
        try:
            previous = cache.get(key) or {}
            current = {str(row['radacctid']): (
                row['acctupdatetime'].timestamp() if row['acctupdatetime'] else None,
                max(row['acctinputoctets'] or 0, 0), max(row['acctoutputoctets'] or 0, 0),
            ) for row in rows}
            old = previous.get('rows', {})
            up = down = samples = 0
            for identity, (stamp, upload, download) in current.items():
                prior = old.get(identity)
                if prior and stamp and prior[0] and 0 < stamp - prior[0] <= FRESH_SECONDS:
                    if upload >= prior[1] and download >= prior[2]:
                        up += (upload - prior[1]) / (stamp - prior[0])
                        down += (download - prior[2]) / (stamp - prior[0])
                        samples += 1
            result = {'upload_bytes_per_second': int(up), 'download_bytes_per_second': int(down),
                      'rate_sampled_sessions': samples} if samples else empty
            # Keep a measured interval visible until the next accounting update.
            if not samples and current and current == old:
                result = previous.get('rates', empty)
            cache.set(key, {'rows': current, 'rates': result}, timeout=FRESH_SECONDS)
            return result
        finally:
            cache.delete(key + ':lock')
    except Exception:
        # Cache availability is optional for speeds, never for financial reads.
        return empty


def network_metrics(tenant):
    now = timezone.now()
    today, _ = boundaries(now)
    addresses = tenant_radius_addresses(tenant)
    qs = Radacct.objects.filter(nasipaddress__in=addresses,
        username__in=Voucher.objects.filter(tenant=tenant).values('username'))
    fresh = fresh_condition(now)
    active_today = Q(acctstarttime__gte=today, acctstarttime__lte=now) | Q(acctupdatetime__gte=today, acctupdatetime__lte=now)
    totals = qs.aggregate(
        online_users=Count('pk', filter=fresh),
        online_vouchers=Count('username', distinct=True, filter=fresh),
        stale_sessions=Count('pk', filter=Q(acctstoptime__isnull=True) & ~fresh),
        sessions_today=Count('pk', filter=Q(acctstarttime__gte=today, acctstarttime__lte=now)),
        live_upload_bytes=Sum('acctinputoctets', filter=fresh),
        live_download_bytes=Sum('acctoutputoctets', filter=fresh),
        today_upload_bytes=Sum('acctinputoctets', filter=active_today),
        today_download_bytes=Sum('acctoutputoctets', filter=active_today),
        all_time_upload_bytes=Sum('acctinputoctets'), all_time_download_bytes=Sum('acctoutputoctets'),
        latest_accounting_at=Max(Coalesce('acctupdatetime', 'acctstarttime')),
    )
    for key in totals:
        if key != 'latest_accounting_at':
            totals[key] = max(totals[key] or 0, 0)
    for period in ['live', 'today', 'all_time']:
        totals[f'{period}_traffic_bytes'] = totals[f'{period}_upload_bytes'] + totals[f'{period}_download_bytes']
    live = qs.filter(fresh)
    per_address = {str(row['nasipaddress']): row['count'] for row in live.values('nasipaddress').annotate(count=Count('pk'))}
    routers = []
    counts = {'online': 0, 'offline': 0, 'unknown': 0, 'awaiting_import': 0, 'inactive': 0}
    for router in NASDevice.objects.filter(tenant=tenant).prefetch_related('onboarding_checks').order_by('name'):
        router_addresses = {str(ip) for ip in [router.ip_address, router.wireguard_ip] if ip} & addresses
        online_users = sum(per_address.get(ip, 0) for ip in router_addresses)
        recent_seen = router.last_seen_at and now - timedelta(seconds=FRESH_SECONDS) <= router.last_seen_at <= now
        confirmed_offline = any(check.check_type == 'ping' and not check.passed
            and check.details.get('outcome') == 'offline'
            and now - timedelta(seconds=FRESH_SECONDS) <= check.checked_at <= now
            and (not router.last_seen_at or check.checked_at > router.last_seen_at)
            for check in router.onboarding_checks.all())
        if not router.is_active or router.onboarding_state == 'suspended':
            state = 'inactive'
        elif online_users:
            state = 'online'
        elif confirmed_offline:
            state = 'offline'
        elif recent_seen:
            state = 'online'
        elif router.onboarding_state in ['pending', 'reviewed', 'approved', 'waiting_for_vpn']:
            state = 'awaiting_import'
        else:
            state = 'unknown'
        counts[state] += 1
        routers.append({'id': str(router.pk), 'name': router.name, 'status': state,
                        'online_users': online_users, 'last_seen_at': router.last_seen_at})
    sample = list(live.values('radacctid', 'acctupdatetime', 'acctinputoctets', 'acctoutputoctets')[:10001])
    return {**totals, **sample_rates(tenant.pk, sample, now),
            'router_counts': counts, 'routers': routers[:20], 'routers_total': len(routers),
            'observed_at': now, 'freshness_seconds': FRESH_SECONDS,
            'traffic_basis': 'cumulative_counters_for_sessions_active_today', 'source': 'radius_accounting'}
