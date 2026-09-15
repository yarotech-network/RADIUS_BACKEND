import uuid
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

class AgentWalletFundingPayment(models.Model):
    funding_terms = models.JSONField(null=True, blank=True)
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
    wallet_transaction = models.OneToOneField("AgentWalletTransaction", null=True, blank=True, on_delete=models.PROTECT, related_name="funding_payment")

    class Meta:
        db_table = "agents_fundingpayment"
        ordering = ["-created_at"]


class AgentVoucherAllocation(models.Model):
    credit_batch = models.ForeignKey('AgentCreditBatch', null=True, blank=True, on_delete=models.PROTECT, related_name='voucher_allocations')
    ALLOCATION_TYPES = [
        ("wallet", "Wallet"),
        ("credit", "Credit"),
        ("complimentary", "Complimentary"),
    ]

    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name="allocations")
    voucher = models.OneToOneField("vouchers.Voucher", on_delete=models.PROTECT, related_name="agent_allocation")
    allocation_type = models.CharField(max_length=20, choices=ALLOCATION_TYPES, default="wallet")
    amount_charged = models.PositiveIntegerField(default=0)  # in kobo
    commission_earned = models.PositiveIntegerField(default=0)  # in kobo
    retail_price = models.PositiveIntegerField(null=True, blank=True)
    commission_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    wallet_transaction = models.ForeignKey("AgentWalletTransaction", null=True, blank=True, on_delete=models.PROTECT, related_name="allocations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_voucherallocation"
        ordering = ["-created_at"]


class AgentWalletTransaction(models.Model):
    """New financial movements; existing balances do not imply invented history."""
    wallet = models.ForeignKey(AgentWallet, on_delete=models.PROTECT, related_name="transactions")
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    category = models.CharField(max_length=20, choices=[("voucher_sale", "Voucher sale"), ("funding", "Wallet funding")])
    amount = models.PositiveIntegerField()
    previous_balance = models.PositiveIntegerField()
    new_balance = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_wallettransaction"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["wallet", "-created_at", "-id"], name="agent_wallet_history_idx")]
        constraints = [models.CheckConstraint(
            condition=(models.Q(category="voucher_sale", previous_balance=models.F("new_balance") + models.F("amount")) |
                       models.Q(category="funding", new_balance=models.F("previous_balance") + models.F("amount"))),
            name="agent_wallet_movement_arithmetic",
        )]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Wallet movements cannot be edited.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Wallet movements cannot be deleted.")


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


class AgentCreditBatch(models.Model):
    """New obligations only. Historical per-voucher records are not guessed into batches."""
    agent = models.ForeignKey(AgentProfile, on_delete=models.PROTECT, related_name='credit_batches')
    plan = models.ForeignKey('vouchers.InternetPlan', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField()
    retail_price = models.PositiveIntegerField()
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    total = models.PositiveIntegerField()
    repaid = models.PositiveIntegerField(default=0)
    cancelled_debt = models.PositiveIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=200, blank=True)

    @property
    def outstanding(self):
        return self.total - self.repaid - self.cancelled_debt

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(total=models.F('unit_price') * models.F('quantity')), name='credit_batch_total'),
            models.CheckConstraint(condition=models.Q(total__gte=models.F('repaid') + models.F('cancelled_debt')), name='credit_batch_settlement'),
            models.CheckConstraint(condition=models.Q(quantity__gte=1, quantity__lte=100), name='credit_batch_quantity'),
        ]


class AgentCreditMovement(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT)
    batch = models.ForeignKey(AgentCreditBatch, on_delete=models.PROTECT, related_name='movements')
    ledger = models.OneToOneField(AgentCreditLedger, on_delete=models.PROTECT, related_name='movement')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=12, choices=[('issue', 'Issue'), ('repay', 'Repayment'), ('reverse', 'Reversal')])
    request_key = models.UUIDField()
    request_payload = models.JSONField()
    external_reference = models.CharField(max_length=100, blank=True)
    method = models.CharField(max_length=30, blank=True)
    received_on = models.DateField(null=True, blank=True)
    previous_balance = models.IntegerField()
    new_balance = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'request_key'], name='credit_request_unique'),
            models.UniqueConstraint(fields=['tenant', 'external_reference'], condition=~models.Q(external_reference=''), name='credit_receipt_reference_unique'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('Credit movements cannot be edited.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Credit movements cannot be deleted.')
