"""Tenant reporting reads. No provider calls, router probes or business writes."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.agents.models import AgentCreditMovement, AgentProfile, AgentVoucherAllocation
from apps.routers.models import NASDevice
from apps.vouchers.models import InternetPlan, PaymentTransaction, Voucher

REPORTING_ZONE = ZoneInfo('Africa/Lagos')


def boundaries(now):
    local = now.astimezone(REPORTING_ZONE)
    today = datetime.combine(local.date(), time.min, tzinfo=REPORTING_ZONE)
    return today, today.replace(day=1)


def revenue(qs, field, date_field, now):
    today, month = boundaries(now)
    return qs.aggregate(
        total=Sum(field),
        today=Sum(field, filter=Q(**{f'{date_field}__gte': today, f'{date_field}__lte': now})),
        month=Sum(field, filter=Q(**{f'{date_field}__gte': month, f'{date_field}__lte': now})),
    )


def business_metrics(tenant):
    now = timezone.now()
    today, _ = boundaries(now)
    vouchers = Voucher.objects.filter(tenant=tenant, deleted_at__isnull=True)
    expired = Q(status='expired') | Q(expires_at__lte=now)
    disabled = Q(status='disabled')
    started = Q(first_used_at__isnull=False) | Q(is_used=True) | Q(status__in=['active', 'used'])
    usable = ~expired & ~disabled
    usage = vouchers.aggregate(
        total=Count('pk'),
        active=Count('pk', filter=usable & started),
        available=Count('pk', filter=usable & ~started & Q(status='unused')),
        sold=Count('pk', filter=Q(status='sold')),
        used=Count('pk', filter=started),
        expired=Count('pk', filter=expired & ~disabled),
        disabled=Count('pk', filter=disabled),
        not_started=Count('pk', filter=usable & ~started),
        issued_today=Count('pk', filter=Q(created_at__gte=today, created_at__lte=now)),
    )
    payments = PaymentTransaction.objects.filter(tenant=tenant)
    payment_counts = payments.aggregate(**{
        state: Count('pk', filter=Q(status=state)) for state in ['success', 'pending', 'failed']
    })
    # Preserve the existing online-payment reporting basis (transaction creation
    # date), also used by the legacy dashboard. Do not infer cash from plan prices.
    online = revenue(payments.filter(status='success'), 'amount', 'created_at', now)
    wallet = revenue(AgentVoucherAllocation.objects.filter(
        agent__tenant=tenant, voucher__tenant=tenant, allocation_type='wallet',
        voucher__payment__isnull=True,
    ), 'amount_charged', 'created_at', now)
    credit = revenue(AgentCreditMovement.objects.filter(tenant=tenant, kind='repay'),
                     'ledger__amount', 'created_at', now)
    # Repayments are negative ledger movements; charges and cancelled debt are not revenue.
    collected = {key: (online[key] or 0) + (wallet[key] or 0) - (credit[key] or 0)
                 for key in ['total', 'today', 'month']}
    plans = InternetPlan.objects.filter(tenant=tenant)
    routers = NASDevice.objects.filter(tenant=tenant)
    return {
        'total_vouchers': usage['total'], 'active_vouchers': usage['active'],
        'voucher_usage': usage, 'vouchers_issued_today': usage['issued_today'],
        'total_revenue': online['total'] or 0,
        'collected_revenue': collected,
        'revenue_sources': {'online': online['total'] or 0, 'agent_wallet': wallet['total'] or 0,
                            'agent_credit_repayments': -(credit['total'] or 0)},
        'successful_payments': payment_counts['success'],
        'pending_payments': payment_counts['pending'], 'failed_payments': payment_counts['failed'],
        'paid_unfulfilled_payments': payments.filter(verified_at__isnull=False, voucher__isnull=True)
            .filter(iot_purchase__fulfilled_at__isnull=True).count(),
        'total_agents': AgentProfile.objects.filter(tenant=tenant).count(),
        'total_routers': routers.count(),
        'active_routers': routers.filter(onboarding_state='active').count(),
        'total_plans': plans.filter(archived_at__isnull=True).count(),
        'active_plans': plans.filter(is_active=True, archived_at__isnull=True).count(),
        'currency': 'NGN', 'amount_unit': 'kobo', 'observed_at': now,
        'reporting_timezone': str(REPORTING_ZONE),
    }
