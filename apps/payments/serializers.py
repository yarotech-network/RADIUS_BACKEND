from rest_framework import serializers

from apps.vouchers.models import InternetPlan


class InitializePaymentSerializer(serializers.Serializer):
    plan_id = serializers.PrimaryKeyRelatedField(
        source="plan",
        queryset=InternetPlan.objects.filter(is_active=True),
    )
    email = serializers.EmailField()
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
