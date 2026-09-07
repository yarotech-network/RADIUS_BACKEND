import django_filters
from django.db import models
from .models import Voucher, PaymentTransaction


class VoucherFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    plan = django_filters.NumberFilter(field_name="plan_id")
    agent = django_filters.NumberFilter(field_name="agent_id")
    search = django_filters.CharFilter(method="filter_search")
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Voucher
        fields = ["status", "plan", "agent", "search"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            models.Q(username__icontains=value) |
            models.Q(agent__user__username__icontains=value)
        )


class PaymentTransactionFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = PaymentTransaction
        fields = ["status", "search"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            models.Q(reference__icontains=value) |
            models.Q(customer_email__icontains=value) |
            models.Q(customer_name__icontains=value)
        )
