from django.db import IntegrityError
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from drf_spectacular.utils import extend_schema, extend_schema_serializer
from apps.core.api import tenant_for
from apps.core.permissions import IsTenantOwner, IsAgent
from .models import AgentCreditBatch, AgentCreditLedger
from .credit import account_summary, configure_credit, execute_credit


class CreditExpectedSerializer(serializers.Serializer):
    exists = serializers.BooleanField()
    credit_limit = serializers.IntegerField(min_value=0, max_value=2147483647)
    is_active = serializers.BooleanField()


class CreditSettingsSerializer(serializers.Serializer):
    credit_limit = serializers.IntegerField(min_value=0, max_value=2147483647)
    is_active = serializers.BooleanField()
    expected = CreditExpectedSerializer()
    note = serializers.CharField(max_length=200)


@extend_schema_serializer(many=False)
class CreditAccountSerializer(CreditExpectedSerializer):
    current_balance = serializers.IntegerField()
    available_credit = serializers.IntegerField()
    requires_review = serializers.BooleanField()


class CreditIssueSerializer(serializers.Serializer):
    request_key = serializers.UUIDField()
    plan_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    expected_total = serializers.IntegerField(min_value=1, max_value=2147483647)
    due_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class CreditRepaymentSerializer(serializers.Serializer):
    request_key = serializers.UUIDField()
    batch_id = serializers.IntegerField(min_value=1)
    amount = serializers.IntegerField(min_value=1, max_value=2147483647)
    external_reference = serializers.CharField(max_length=100)
    method = serializers.ChoiceField(choices=['cash', 'bank_transfer', 'other'])
    received_on = serializers.DateField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class CreditReversalSerializer(serializers.Serializer):
    request_key = serializers.UUIDField()
    batch_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=200)
    expected_outstanding = serializers.IntegerField(min_value=0, max_value=2147483647)
    expected_repaid = serializers.IntegerField(min_value=0, max_value=2147483647)


class CreditBatchSerializer(serializers.ModelSerializer):
    outstanding = serializers.IntegerField(read_only=True)
    class Meta:
        model = AgentCreditBatch
        fields = ['id', 'plan', 'quantity', 'unit_price', 'retail_price', 'commission_rate', 'total',
                  'repaid', 'cancelled_debt', 'outstanding', 'due_date', 'note', 'created_at',
                  'reversed_at', 'reversal_reason']


class CreditLedgerSerializer(serializers.ModelSerializer):
    evidence = serializers.SerializerMethodField()
    class Meta:
        model = AgentCreditLedger
        fields = ['id', 'amount', 'description', 'created_at', 'evidence']

    def get_evidence(self, obj) -> dict | None:
        movement = getattr(obj, 'movement', None)
        if not movement:
            return None
        return {'batch_id': movement.batch_id, 'kind': movement.kind, 'actor_id': movement.actor_id,
                'external_reference': movement.external_reference, 'method': movement.method,
                'received_on': movement.received_on, 'previous_balance': movement.previous_balance,
                'new_balance': movement.new_balance}


class AgentCreditActions:
    @extend_schema(methods=['GET'], responses=CreditAccountSerializer)
    @extend_schema(methods=['PATCH'], request=CreditSettingsSerializer, responses=CreditAccountSerializer)
    @action(detail=True, methods=['get', 'patch'], permission_classes=[IsTenantOwner])
    def credit(self, request, pk=None):
        agent = self.get_object()
        if request.method == 'GET':
            return Response(account_summary(agent))
        serializer = CreditSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(configure_credit(tenant_for(request), agent.pk, request.user, serializer.validated_data))

    @extend_schema(responses=CreditBatchSerializer(many=True))
    @action(detail=True, methods=['get'], url_path='credit-batches', permission_classes=[IsTenantOwner])
    def credit_batches(self, request, pk=None):
        query = AgentCreditBatch.objects.filter(agent=self.get_object())
        return self.get_paginated_response(CreditBatchSerializer(self.paginate_queryset(query), many=True).data)

    @extend_schema(responses=CreditLedgerSerializer(many=True))
    @action(detail=True, methods=['get'], url_path='credit-history', permission_classes=[IsTenantOwner])
    def credit_history(self, request, pk=None):
        query = AgentCreditLedger.objects.filter(credit_account__agent=self.get_object()).select_related('movement').order_by('-created_at', '-id')
        return self.get_paginated_response(CreditLedgerSerializer(self.paginate_queryset(query), many=True).data)

    def _credit_command(self, request, kind, serializer_class):
        agent = self.get_object()
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        # serializer.data provides canonical JSON-safe dates for durable payload comparison.
        payload = dict(serializer.data)
        key = payload.pop('request_key')
        try:
            batch = execute_credit(tenant_for(request), agent.pk, request.user, kind, key, payload)
        except IntegrityError:
            from .models import AgentCreditMovement
            conflicts = AgentCreditMovement.objects.filter(tenant=tenant_for(request), request_key=key).exists()
            if payload.get('external_reference'):
                conflicts = conflicts or AgentCreditMovement.objects.filter(tenant=tenant_for(request), external_reference=payload['external_reference']).exists()
            if not conflicts:
                raise
            return Response({'detail': 'Receipt reference or request key already exists. Refresh and reconcile before retrying.'}, status=409)
        return Response(CreditBatchSerializer(batch).data)

    @extend_schema(request=CreditIssueSerializer, responses=CreditBatchSerializer)
    @action(detail=True, methods=['post'], url_path='credit-issue', permission_classes=[IsTenantOwner])
    def credit_issue(self, request, pk=None):
        return self._credit_command(request, 'issue', CreditIssueSerializer)

    @extend_schema(request=CreditRepaymentSerializer, responses=CreditBatchSerializer)
    @action(detail=True, methods=['post'], url_path='credit-repay', permission_classes=[IsTenantOwner])
    def credit_repay(self, request, pk=None):
        return self._credit_command(request, 'repay', CreditRepaymentSerializer)

    @extend_schema(request=CreditReversalSerializer, responses=CreditBatchSerializer)
    @action(detail=True, methods=['post'], url_path='credit-reverse', permission_classes=[IsTenantOwner])
    def credit_reverse(self, request, pk=None):
        return self._credit_command(request, 'reverse', CreditReversalSerializer)


class AgentOwnCreditViewSet(GenericViewSet):
    permission_classes = [IsAgent]
    serializer_class = CreditBatchSerializer

    @extend_schema(responses=CreditAccountSerializer, filters=False)
    def list(self, request):
        return Response(account_summary(request.user.agent_profile))

    @extend_schema(responses=CreditBatchSerializer(many=True))
    @action(detail=False, methods=['get'])
    def batches(self, request):
        query = AgentCreditBatch.objects.filter(agent=request.user.agent_profile)
        return self.get_paginated_response(CreditBatchSerializer(self.paginate_queryset(query), many=True).data)

    @extend_schema(responses=CreditLedgerSerializer(many=True))
    @action(detail=False, methods=['get'])
    def history(self, request):
        query = AgentCreditLedger.objects.filter(credit_account__agent=request.user.agent_profile).select_related('movement').order_by('-created_at', '-id')
        return self.get_paginated_response(CreditLedgerSerializer(self.paginate_queryset(query), many=True).data)
