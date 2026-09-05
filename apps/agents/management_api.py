from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from apps.core.api import tenant_for, audit
from apps.core.commands import idempotent
from apps.core.permissions import IsTenantManager
from .models import AgentProfile, AgentWallet
from .serializers import AgentProfileSerializer
from drf_spectacular.utils import extend_schema


class AgentCreateSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=3, max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True, trim_whitespace=False)
    phone = serializers.CharField(min_length=10, max_length=20)
    shop_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False)

    def validate(self, attrs):
        User = get_user_model()
        if User.objects.filter(username=attrs["username"]).exists():
            raise ValidationError({"username": "Username already taken."})
        if User.objects.filter(email__iexact=attrs["email"]).exists():
            raise ValidationError({"email": "Email already registered."})
        validate_password(attrs["password"], User(username=attrs["username"], email=attrs["email"]))
        return attrs


class AgentEditSerializer(serializers.ModelSerializer):
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False)
    class Meta:
        model = AgentProfile
        fields = ["phone", "shop_name", "commission_rate"]


class AgentManagementViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsTenantManager]
    serializer_class = AgentProfileSerializer
    filterset_fields = ["status"]
    search_fields = ["user__username", "shop_name", "phone"]
    ordering_fields = ["created_at", "id"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AgentProfile.objects.none()
        return AgentProfile.objects.filter(tenant=tenant_for(self.request)).select_related("user", "wallet")

    def get_serializer_class(self):
        return {"create": AgentCreateSerializer, "partial_update": AgentEditSerializer}.get(self.action, AgentProfileSerializer)

    @extend_schema(request=AgentCreateSerializer, responses={201: AgentProfileSerializer})
    @idempotent
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                username=values.pop("username"), email=values.pop("email"), password=values.pop("password"), phone=values["phone"],
            )
            agent = AgentProfile.objects.create(user=user, tenant=tenant_for(request), **values)
            AgentWallet.objects.create(agent=agent)
            audit(request, "agent.created", agent)
        return Response(AgentProfileSerializer(agent).data, status=201)

    @extend_schema(request=AgentEditSerializer, responses=AgentProfileSerializer)
    def partial_update(self, request, pk=None):
        agent = self.get_object()
        with transaction.atomic():
            agent = AgentProfile.objects.select_for_update().get(pk=agent.pk)
            serializer = self.get_serializer(agent, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            audit(request, "agent.updated", agent, {"fields": list(serializer.validated_data)})
        return Response(AgentProfileSerializer(agent).data)

    @extend_schema(request=None, responses=AgentProfileSerializer)
    @action(detail=True, methods=["post"])
    @idempotent
    def approve(self, request, pk=None):
        return self.change_status(request, "active")

    @extend_schema(request=None, responses=AgentProfileSerializer)
    @action(detail=True, methods=["post"])
    @idempotent
    def suspend(self, request, pk=None):
        return self.change_status(request, "suspended")

    def change_status(self, request, target):
        agent = self.get_object()
        with transaction.atomic():
            agent = AgentProfile.objects.select_for_update().get(pk=agent.pk)
            if agent.status != target:
                previous = agent.status
                agent.status = target
                agent.save(update_fields=["status"])
                audit(request, "agent.status_changed", agent, {"from": previous, "to": target})
        return Response(AgentProfileSerializer(agent).data)
