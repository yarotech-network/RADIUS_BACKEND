from django.db import models
from django.conf import settings


class AgentProfile(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("suspended", "Suspended"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_profile")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="agents")
    phone = models.CharField(max_length=20)
    shop_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_agentprofile"

    def __str__(self):
        return f"Agent: {self.user.username}"


class AgentWallet(models.Model):
    agent = models.OneToOneField(AgentProfile, on_delete=models.CASCADE, related_name="wallet")
    balance = models.PositiveIntegerField(default=0)  # in kobo
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agents_wallet"

    def __str__(self):
        return f"Wallet: {self.agent.user.username} (\u20a6{self.balance / 100})"

    def credit(self, amount):
        self.balance += amount
        self.save(update_fields=["balance", "updated_at"])

    def debit(self, amount):
        if self.balance < amount:
            raise ValueError("Insufficient balance")
        self.balance -= amount
        self.save(update_fields=["balance", "updated_at"])


class AgentWalletFundingPayment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    wallet = models.ForeignKey(AgentWallet, on_delete=models.CASCADE, related_name="funding_payments")
    amount = models.PositiveIntegerField(help_text="Amount in kobo")
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    paystack_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agents_fundingpayment"
        ordering = ["-created_at"]


class AgentVoucherAllocation(models.Model):
    ALLOCATION_TYPES = [
        ("wallet", "Wallet"),
        ("credit", "Credit"),
        ("complimentary", "Complimentary"),
    ]

    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name="allocations")
    voucher = models.OneToOneField("vouchers.Voucher", on_delete=models.CASCADE, related_name="agent_allocation")
    allocation_type = models.CharField(max_length=20, choices=ALLOCATION_TYPES, default="wallet")
    amount_charged = models.PositiveIntegerField(default=0)  # in kobo
    commission_earned = models.PositiveIntegerField(default=0)  # in kobo
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_voucherallocation"
        ordering = ["-created_at"]


class AgentCreditAccount(models.Model):
    agent = models.OneToOneField(AgentProfile, on_delete=models.CASCADE, related_name="credit_account")
    credit_limit = models.PositiveIntegerField(default=0)  # in kobo
    current_balance = models.IntegerField(default=0)  # positive = owed to tenant, negative = credit remaining
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_creditaccount"


class AgentCreditLedger(models.Model):
    credit_account = models.ForeignKey(AgentCreditAccount, on_delete=models.CASCADE, related_name="ledger_entries")
    amount = models.IntegerField(help_text="Positive = charge, negative = payment")
    description = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_creditledger"
        ordering = ["-created_at"]
