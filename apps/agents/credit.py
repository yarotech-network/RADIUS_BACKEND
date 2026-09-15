"""Operator credit commands; all writes use the default database, with no network calls.

Lock order: agent, plan (issuance only), account, batch, vouchers by primary key.
The agent lock also serializes first-account creation and same-agent command retries.
Tenant-wide receipt/key uniqueness arbitrates conflicting commands across agents.
"""
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Lower
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.core.models import AuditEvent
from apps.tenants.models import TenantMembership
from apps.vouchers.models import InternetPlan, Voucher, Radcheck, Radreply, Radacct, Radpostauth
from apps.vouchers.services import VoucherService
from .models import (AgentProfile, AgentCreditAccount, AgentCreditLedger,
                     AgentCreditBatch, AgentCreditMovement, AgentVoucherAllocation)
from .pricing import agent_price


def _agent(tenant, agent_id, actor):
    if not actor.is_active or not TenantMembership.objects.filter(
        user=actor, tenant=tenant, role='owner', is_active=True,
    ).exists():
        raise PermissionDenied('Only the tenant owner can manage agent credit.')
    return AgentProfile.objects.select_for_update().get(pk=agent_id, tenant=tenant)


def account_summary(agent):
    account = AgentCreditAccount.objects.filter(agent=agent).first()
    if account is None:
        return dict(exists=False, credit_limit=0, current_balance=0, is_active=False,
                    available_credit=0, requires_review=False)
    total = account.ledger_entries.aggregate(total=Sum('amount'))['total'] or 0
    review = account.current_balance < 0 or total != account.current_balance
    return dict(exists=True, credit_limit=account.credit_limit, current_balance=account.current_balance,
                is_active=account.is_active, requires_review=review,
                available_credit=max(0, account.credit_limit-account.current_balance) if account.is_active and not review else 0)


@transaction.atomic
def configure_credit(tenant, agent_id, actor, values):
    agent = _agent(tenant, agent_id, actor)
    before = account_summary(agent)
    expected = values['expected']
    if any(before[key] != expected[key] for key in ('exists', 'credit_limit', 'is_active')):
        raise ValidationError('Credit settings changed. Refresh before saving.')
    account, _ = AgentCreditAccount.objects.get_or_create(agent=agent)
    account.credit_limit = values['credit_limit']
    account.is_active = values['is_active']
    account.save(update_fields=['credit_limit', 'is_active'])
    AuditEvent.objects.create(tenant=tenant, actor=actor, action='agent.credit_configured',
        resource=f'agents.agentprofile:{agent.pk}', details={'before': before,
            'credit_limit': account.credit_limit, 'is_active': account.is_active, 'note': values['note']})
    return account_summary(agent)


def _movement(tenant, batch, account, actor, kind, key, payload, amount):
    previous = account.current_balance
    following = previous + amount
    if not 0 <= following <= 2147483647:
        raise ValidationError('Credit balance requires reconciliation or exceeds the supported range.')
    ledger = AgentCreditLedger.objects.create(credit_account=account, amount=amount,
        description=payload.get('note') or payload.get('reason') or f'Credit {kind}, allocation {batch.pk}')
    AgentCreditMovement.objects.create(tenant=tenant, batch=batch, ledger=ledger, actor=actor,
        kind=kind, request_key=key, request_payload=payload, previous_balance=previous, new_balance=following,
        external_reference=payload.get('external_reference', ''), method=payload.get('method', ''),
        received_on=payload.get('received_on'))
    account.current_balance = following
    account.save(update_fields=['current_balance'])


@transaction.atomic
def execute_credit(tenant, agent_id, actor, kind, key, payload):
    if kind == 'issue' and (type(payload.get('quantity')) is not int or not 1 <= payload['quantity'] <= 100):
        raise ValidationError('Quantity must be between 1 and 100.')
    if kind == 'repay' and (type(payload.get('amount')) is not int or not 0 < payload['amount'] <= 2147483647):
        raise ValidationError('Repayment must be a positive amount in kobo.')
    agent = _agent(tenant, agent_id, actor)
    previous = AgentCreditMovement.objects.filter(tenant=tenant, request_key=key).select_related('batch').first()
    if previous:
        if previous.kind != kind or previous.request_payload != payload or previous.batch.agent_id != agent.pk:
            raise ValidationError('Request key was already used for different credit instructions.')
        return previous.batch
    if kind == 'issue':
        plan = InternetPlan.objects.select_for_update().filter(pk=payload['plan_id'], tenant=tenant,
            is_active=True, agent_enabled=True, archived_at__isnull=True, plan_type='voucher').first()
        if plan is None or agent.status != 'active' or not tenant.is_active:
            raise ValidationError('Agent, tenant or plan is unavailable for new credit vouchers.')
    account = AgentCreditAccount.objects.select_for_update().filter(agent=agent).first()
    if account is None or account_summary(agent)['requires_review']:
        raise ValidationError('Configure or reconcile this credit account before continuing.')
    if kind == 'issue':
        price = agent_price(plan.price, agent.commission_rate)
        total = price['agent_cost'] * payload['quantity']
        if total != payload['expected_total']:
            raise ValidationError('The price changed. Review the current price before issuing credit.')
        if not account.is_active or account.credit_limit <= 0 or total <= 0 or account.current_balance + total > account.credit_limit:
            raise ValidationError('An active, sufficient configured credit limit is required.')
        batch = AgentCreditBatch.objects.create(agent=agent, plan=plan, quantity=payload['quantity'],
            unit_price=price['agent_cost'], retail_price=plan.price, commission_rate=agent.commission_rate,
            total=total, due_date=payload.get('due_date'), note=payload.get('note', ''))
        vouchers = VoucherService.generate_vouchers(tenant, plan.pk, payload['quantity'], agent=agent, source='agent',
            prefix=tenant.settings.voucher_prefix if hasattr(tenant, 'settings') else '')
        AgentVoucherAllocation.objects.bulk_create([
            AgentVoucherAllocation(agent=agent, voucher=voucher, credit_batch=batch, allocation_type='credit',
                amount_charged=price['agent_cost'], commission_earned=price['commission_amount'],
                retail_price=plan.price, commission_rate_snapshot=agent.commission_rate) for voucher in vouchers])
        _movement(tenant, batch, account, actor, kind, key, payload, total)
        return batch
    batch = AgentCreditBatch.objects.select_for_update().filter(pk=payload['batch_id'], agent=agent).first()
    if batch is None:
        raise ValidationError('Credit allocation not found.')
    if kind == 'repay':
        if batch.reversed_at or payload['amount'] > batch.outstanding or payload['amount'] > account.current_balance:
            raise ValidationError('Repayment exceeds the remaining debt or the allocation was cancelled.')
        if AgentCreditMovement.objects.filter(tenant=tenant, external_reference=payload['external_reference']).exists():
            raise ValidationError('This receipt reference has already been recorded.')
        batch.repaid += payload['amount']
        batch.save(update_fields=['repaid'])
        _movement(tenant, batch, account, actor, kind, key, payload, -payload['amount'])
        return batch
    if kind != 'reverse':
        raise ValidationError('Unknown credit operation.')
    if batch.reversed_at:
        return batch
    if batch.outstanding != payload['expected_outstanding'] or batch.repaid != payload['expected_repaid']:
        raise ValidationError('Allocation payments changed. Refresh and review the cancellation amounts.')
    vouchers = list(Voucher.objects.select_for_update().filter(agent_allocation__credit_batch=batch).order_by('pk'))
    if len(vouchers) != batch.quantity:
        raise ValidationError('Allocation voucher mapping requires reconciliation.')
    for voucher in vouchers:
        if (voucher.tenant_id != tenant.pk or voucher.agent_id != agent.pk
            or voucher.status not in ('unused', 'sold') or voucher.legacy_provenance
            or voucher.is_used or voucher.deleted_at or voucher.activated_at or voucher.first_used_at
            or voucher.last_used_at or voucher.used_at or voucher.bound_device_mac or voucher.device_bound_at
            or voucher.device_bound_nas_id or (voucher.expires_at and voucher.expires_at <= timezone.now())):
            raise ValidationError('Used, expired, bound or uncertain vouchers cannot be cancelled.')
    usernames = [voucher.username for voucher in vouchers]
    # Any authentication history is conservative evidence of possible consumption.
    from apps.customers.models import DeviceAccessSession
    identities = [name.lower() for name in usernames]
    if (Radacct.objects.annotate(identity=Lower('username')).filter(identity__in=identities).exists()
        or Radpostauth.objects.annotate(identity=Lower('username')).filter(identity__in=identities).exists()
        or DeviceAccessSession.objects.filter(voucher__in=vouchers).exists()):
        raise ValidationError('Voucher authentication/accounting history prevents cancellation.')
    cancelled = batch.outstanding
    if cancelled > account.current_balance:
        raise ValidationError('Account debt requires reconciliation.')
    Voucher.objects.filter(pk__in=[voucher.pk for voucher in vouchers]).update(status='disabled')
    Radcheck.objects.filter(username__in=usernames).delete()
    Radreply.objects.filter(username__in=usernames).delete()
    batch.cancelled_debt = cancelled
    batch.reversed_at = timezone.now()
    batch.reversal_reason = payload['reason']
    batch.save(update_fields=['cancelled_debt', 'reversed_at', 'reversal_reason'])
    _movement(tenant, batch, account, actor, kind, key, payload, -cancelled)
    return batch
