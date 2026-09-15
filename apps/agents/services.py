from django.db import transaction
from .models import (
    AgentProfile,
    AgentWallet,
    AgentVoucherAllocation,
    AgentCreditAccount,
    AgentWalletFundingPayment,
    AgentWalletTransaction,
)
from apps.vouchers.services import VoucherService
from .pricing import agent_price
from .funding_terms import funding_policy, reserve_funding_terms, funding_total


def _record_movement(wallet, amount, category):
    """Caller holds the wallet row lock inside the operation's atomic block."""
    if type(amount) is not int or amount < 0:
        raise ValueError('Invalid wallet amount.')
    previous = wallet.balance
    following = previous - amount if category == 'voucher_sale' else previous + amount
    if not 0 <= following <= 2147483647 or amount > 2147483647:
        raise ValueError('Wallet movement exceeds the supported balance range.')
    wallet.balance = following
    wallet.save(update_fields=['balance', 'updated_at'])
    return AgentWalletTransaction.objects.create(wallet=wallet, category=category,
        amount=amount, previous_balance=previous, new_balance=following)


class AgentService:
    """Agent wallet and voucher operations."""

    @staticmethod
    @transaction.atomic
    def generate_voucher_from_wallet(agent, plan_id, quantity=1):
        """Generate vouchers funded from agent's wallet."""
        if type(quantity) is not int or not 1 <= quantity <= 100:
            raise ValueError("Quantity must be an integer between 1 and 100.")
        agent = AgentProfile.objects.select_for_update(of=('self',)).select_related("tenant").get(pk=agent.pk)
        if agent.status != "active" or not agent.tenant.is_active:
            raise ValueError("Agent or tenant is inactive.")
        from apps.vouchers.models import InternetPlan
        try:
            plan = InternetPlan.objects.select_for_update().get(id=plan_id, is_active=True, agent_enabled=True, archived_at__isnull=True, plan_type='voucher', tenant=agent.tenant)
        except (InternetPlan.DoesNotExist, TypeError, ValueError) as exc:
            raise ValueError("Plan not found or inactive.") from exc
        wallet = AgentWallet.objects.select_for_update().get(agent=agent)
        price = agent_price(plan.price, agent.commission_rate)
        total_cost = price['agent_cost'] * quantity

        if wallet.balance < total_cost:
            raise ValueError("Insufficient wallet balance")

        # Debit wallet
        movement = _record_movement(wallet, total_cost, 'voucher_sale')

        # Generate vouchers
        vouchers = VoucherService.generate_vouchers(
            tenant=agent.tenant,
            plan_id=plan_id,
            quantity=quantity,
            prefix=agent.tenant.settings.voucher_prefix if hasattr(agent.tenant, "settings") else "",
            agent=agent,
            source="agent",
        )

        # Create allocation records
        allocations = []
        for voucher in vouchers:
            allocation = AgentVoucherAllocation.objects.create(
                agent=agent,
                voucher=voucher,
                allocation_type="wallet",
                amount_charged=price['agent_cost'],
                commission_earned=price['commission_amount'],
                retail_price=plan.price,
                commission_rate_snapshot=agent.commission_rate,
                wallet_transaction=movement,
            )
            allocations.append(allocation)

        return vouchers, allocations

    @staticmethod
    @transaction.atomic
    def fund_wallet(agent, amount, reference, expected_total=None):
        """Initialize wallet funding via Paystack."""
        if type(amount) is not int or not 0 < amount <= 2147483647:
            raise ValueError('Invalid wallet funding amount.')
        wallet, _ = AgentWallet.objects.get_or_create(agent=agent)
        from apps.tenants.models import TenantSetting
        setting = TenantSetting.objects.select_for_update().filter(tenant=agent.tenant).first()
        terms = reserve_funding_terms(amount, funding_policy(setting))
        if terms['fee'] and expected_total is None:
            raise ValueError('Confirm the total including funding fees before continuing.')
        if expected_total is not None and expected_total != terms['total']:
            raise ValueError('Funding fees changed. Refresh the quote before continuing.')
        payment = AgentWalletFundingPayment.objects.create(
            wallet=wallet,
            amount=amount,
            reference=reference,
            funding_terms=terms,
        )
        return payment

    @staticmethod
    @transaction.atomic
    def complete_wallet_funding(payment, verified):
        """Credit wallet after successful payment."""
        payment = AgentWalletFundingPayment.objects.select_for_update().get(pk=payment.pk)
        if (not isinstance(verified, dict) or verified.get('status') != 'success'
                or verified.get('reference') != payment.reference
                or type(verified.get('amount')) is not int or verified['amount'] != funding_total(payment)
                or verified.get('currency') != 'NGN'):
            raise ValueError('Wallet funding verification mismatch.')
        if payment.status == "success":
            return False
        if payment.amount <= 0:
            raise ValueError('Invalid wallet funding amount.')

        wallet = AgentWallet.objects.select_for_update().get(pk=payment.wallet_id)
        movement = _record_movement(wallet, payment.amount, 'funding')
        payment.wallet_transaction = movement
        payment.status = "success"
        from django.utils import timezone
        payment.completed_at = timezone.now()
        payment.save(update_fields=["status", "completed_at", "wallet_transaction"])
        return True

    @staticmethod
    def get_agent_stats(agent):
        """Get agent dashboard statistics."""
        wallet, _ = AgentWallet.objects.get_or_create(agent=agent)
        from apps.vouchers.models import Voucher
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.localdate()
        month_start = today.replace(day=1)

        vouchers_today = AgentVoucherAllocation.objects.filter(
            agent=agent, created_at__date=today
        ).count()

        from django.db.models import Sum
        commission_this_month = AgentVoucherAllocation.objects.filter(
            agent=agent, created_at__date__gte=month_start
        ).filter(credit_batch__reversed_at__isnull=True).aggregate(total=Sum("commission_earned"))["total"] or 0

        return {
            "wallet_balance": wallet.balance,
            "vouchers_today": vouchers_today,
            "commission_this_month": commission_this_month,
            "total_vouchers": AgentVoucherAllocation.objects.filter(agent=agent).count(),
        }
