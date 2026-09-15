from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    has_service = serializers.BooleanField(read_only=True)
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj):
        return obj.name or obj.phone or obj.email or obj.reference
    class Meta:
        model = Customer
        fields = ["id", "has_service", "display_name", "mac_address", "reference", "name", "email", "phone", "address", "notes", "archived_at", "created_at", "updated_at"]
        read_only_fields = ["id", "archived_at", "created_at", "updated_at"]
        validators = []  # Tenant and normalized reference are checked under the tenant write lock.

    def validate(self, attrs):
        allowed = {name for name, field in self.fields.items() if not field.read_only}
        if set(self.initial_data) - allowed:
            raise serializers.ValidationError("Unknown or read-only customer fields are not accepted.")
        if self.instance and self.instance.archived_at:
            raise serializers.ValidationError("Restore this customer before editing.")
        return attrs

    def validate_reference(self, value):
        value = value.upper()
        if self.instance and value != self.instance.reference:
            raise serializers.ValidationError("Customer references cannot be changed.")
        query = Customer.objects.filter(tenant=self.context["tenant"], reference__iexact=value)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise serializers.ValidationError("This customer reference already exists, including archived records.")
        return value


class ImportRequestSerializer(serializers.Serializer):
    csv = serializers.CharField(max_length=262144, trim_whitespace=False)
    preview_token = serializers.CharField(max_length=1000, required=False)

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("Unknown import fields are not accepted.")
        if len(attrs["csv"].encode("utf-8")) > 262144:
            raise serializers.ValidationError({"csv": "CSV must be at most 256 KiB."})
        return attrs


class PreviewRowSerializer(serializers.Serializer):
    reference = serializers.CharField()
    name = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    mac_address = serializers.CharField(required=False, allow_blank=True)


class ImportPreviewSerializer(serializers.Serializer):
    preview_token = serializers.CharField()
    count = serializers.IntegerField()
    rows = PreviewRowSerializer(many=True)


class ImportResultSerializer(serializers.Serializer):
    count = serializers.IntegerField()


class CustomerPurchaseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    amount = serializers.IntegerField(help_text='NGN kobo')
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
    plan_name = serializers.SerializerMethodField()
    fulfilled = serializers.SerializerMethodField()

    def get_plan_name(self, obj):
        terms = obj.purchased_terms if isinstance(obj.purchased_terms, dict) else {}
        return terms.get('name') or (obj.plan.name if obj.plan and obj.plan.tenant_id == obj.tenant_id else '')

    def get_fulfilled(self, obj):
        if hasattr(obj, 'iot_purchase'):
            return bool(obj.status == 'success' and obj.verified_at and obj.iot_purchase.fulfilled_at and obj.iot_purchase.tenant_id == obj.tenant_id)
        return bool(obj.status == 'success' and obj.verified_at and obj.voucher_id
            and obj.voucher.tenant_id == obj.tenant_id and obj.voucher.customer_id == obj.customer_id)
