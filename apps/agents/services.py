from django.db import transaction
from .models import (
    AgentProfile,
    AgentWallet,
    AgentVoucherAllocation,
    AgentCreditAccount,
    AgentWalletFundingPayment,
)
from apps.vouchers.services import VoucherService


class AgentService:
    """Agent wallet and voucher operations."""

    @staticmethod
    @transaction.atomic
    def generate_voucher_from_wallet(agent, plan_id, quantity=1):
        """Generate vouchers funded from agent's wallet."""
        if type(quantity) is not int or not 1 <= quantity <= 100:
            raise ValueError("Quantity must be an integer between 1 and 100.")
        agent = AgentProfile.objects.select_for_update().select_related("tenant").get(pk=agent.pk)
        if agent.status != "active" or not agent.tenant.is_active:
            raise ValueError("Agent or tenant is inactive.")
        from apps.vouchers.models import InternetPlan
        try:
            plan = InternetPlan.objects.get(id=plan_id, is_active=True, tenant=agent.tenant)
        except (InternetPlan.DoesNotExist, TypeError, ValueError) as exc:
            raise ValueError("Plan not found or inactive.") from exc
        wallet = AgentWallet.objects.select_for_update().get(agent=agent)
        total_cost = plan.price * quantity

        if wallet.balance < total_cost:
            raise ValueError("Insufficient wallet balance")

        # Debit wallet
        wallet.debit(total_cost)

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
                amount_charged=plan.price,
            )
            allocations.append(allocation)

        return vouchers, allocations

    @staticmethod
    @transaction.atomic
    def fund_wallet(agent, amount, reference):
        """Initialize wallet funding via Paystack."""
        wallet, _ = AgentWallet.objects.get_or_create(agent=agent)
        payment = AgentWalletFundingPayment.objects.create(
            wallet=wallet,
            amount=amount,
            reference=reference,
        )
        return payment

    @staticmethod
    @transaction.atomic
    def complete_wallet_funding(payment):
        """Credit wallet after successful payment."""
        payment = AgentWalletFundingPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == "success":
            return False

        wallet = AgentWallet.objects.select_for_update().get(pk=payment.wallet_id)
        payment.status = "success"
        from django.utils import timezone
        payment.completed_at = timezone.now()
        payment.save(update_fields=["status", "completed_at"])
        wallet.credit(payment.amount)
        return True

    @staticmethod
    def get_agent_stats(agent):
        """Get agent dashboard statistics."""
        wallet, _ = AgentWallet.objects.get_or_create(agent=agent)
        from apps.vouchers.models import Voucher
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.now().date()
        month_start = today.replace(day=1)

        vouchers_today = AgentVoucherAllocation.objects.filter(
            agent=agent, created_at__date=today
        ).count()

        from django.db.models import Sum
        commission_this_month = AgentVoucherAllocation.objects.filter(
            agent=agent, created_at__date__gte=month_start
        ).aggregate(total=Sum("commission_earned"))["total"] or 0

        return {
            "wallet_balance": wallet.balance,
            "vouchers_today": vouchers_today,
            "commission_this_month": commission_this_month,
            "total_vouchers": AgentVoucherAllocation.objects.filter(agent=agent).count(),
        }
