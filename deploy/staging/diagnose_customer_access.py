from django.db import connection
from django.db.models import Q, Max
from apps.vouchers.models import Radacct
from apps.customers.models import DeviceAccessSession, DeviceAccessSync
from apps.routers.models import NASDevice
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    assert cursor.fetchone()[0] == 'yarotech_radius_staging'
print('Accounting rows:', Radacct.objects.count())
print('Rows missing MAC:', Radacct.objects.filter(Q(callingstationid__isnull=True) | Q(callingstationid='')).count())
print('Latest accounting:', Radacct.objects.aggregate(latest=Max('acctupdatetime')))
print('Observed sessions:', DeviceAccessSession.objects.count())
print('Sync:', list(DeviceAccessSync.objects.values('completed_at', 'missing_mac_rows')))
print('Router records:', NASDevice.objects.count())
print('Read-only diagnostic; no credentials or customer identities displayed.')

from apps.customers.device_access_sync import canonical_mac
from apps.vouchers.models import Voucher
owners = {}
for router in NASDevice.objects.all():
    for ip in {str(v) for v in (router.ip_address, router.wireguard_ip) if v}:
        owners.setdefault(ip, []).append(router.tenant_id)
vouchers = dict(Voucher.objects.values_list('username', 'tenant_id'))
counts = dict(unknown_voucher=0, ambiguous_or_missing_nas=0, tenant_mismatch=0, invalid_mac=0, eligible=0)
for row in Radacct.objects.filter(acctstarttime__isnull=False).iterator(chunk_size=1000):
    tenant = vouchers.get(row.username)
    tenants = owners.get(str(row.nasipaddress), [])
    if tenant is None:
        counts['unknown_voucher'] += 1
    elif len(tenants) != 1:
        counts['ambiguous_or_missing_nas'] += 1
    elif tenants[0] != tenant:
        counts['tenant_mismatch'] += 1
    elif not canonical_mac(row.callingstationid):
        counts['invalid_mac'] += 1
    else:
        counts['eligible'] += 1
print('Accounting attribution:', counts)
