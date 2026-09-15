from apps.core.api import tenant_for, platform_context
from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from django.db.models import Count, Exists, OuterRef
from .models import Tenant, TenantMembership, TenantSetting
from .serializers import TenantSerializer, TenantMembershipSerializer, TenantSettingSerializer
from apps.core.permissions import IsPlatformAdmin, IsTenantManager, IsTenantOwner
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied
from .serializers import TenantProfileSerializer
from apps.core.api import audit
from rest_framework.decorators import action
from rest_framework.throttling import ScopedRateThrottle
from apps.accounts.identity import send_owner_setup


class TenantViewSet(viewsets.ModelViewSet):
    """Platform admins see all tenants; owners see their own."""
    serializer_class = TenantSerializer
    filterset_fields = ["is_active", "is_platform_admin"]
    search_fields = ["name", "slug"]

    throttle_scope = None

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        owner = TenantMembership.objects.get(tenant_id=response.data["id"], role="owner").user
        sent = send_owner_setup(owner)
        response.data["owner_delivery_status"] = "sent" if sent else "failed"
        return response

    @action(detail=True, methods=["post"], url_path="resend-owner-setup",
            throttle_classes=[ScopedRateThrottle], throttle_scope="email_resend")
    def resend_owner_setup(self, request, pk=None):
        tenant = self.get_object()
        membership = tenant.memberships.select_related("user").filter(
            role="owner", is_active=True, user__owner_setup_pending=True, user__is_active=True).first()
        if membership is None:
            raise ValidationError("No pending owner setup exists for this tenant.")
        sent = send_owner_setup(membership.user)
        return Response({"owner_delivery_status": "sent" if sent else "failed"}, status=200 if sent else 503)

    @transaction.atomic
    def perform_create(self, serializer):
        from apps.subscriptions.trials import assign_new_tenant_trial
        tenant = serializer.save()
        assign_new_tenant_trial(tenant)
        audit(self.request, "tenant.created", tenant)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Tenant.objects.none()
        queryset = Tenant.objects.all()
        if not platform_context(self.request):
            queryset = queryset.filter(memberships__user=self.request.user,
                memberships__is_active=True, is_active=True)
        return queryset.annotate(
            member_count=Count("memberships", distinct=True),
            voucher_count=Count("vouchers", distinct=True),
            pending_owner_setup=Exists(TenantMembership.objects.filter(
                tenant_id=OuterRef("pk"), role="owner", user__owner_setup_pending=True)),
        ).order_by("-created_at", "-id")

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsPlatformAdmin()]


class TenantMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = TenantMembershipSerializer
    filterset_fields = ["role", "user", "tenant"]
    ordering = ["id"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [(IsPlatformAdmin | IsTenantOwner)()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TenantMembership.objects.none()
        if platform_context(self.request):
            return TenantMembership.objects.select_related("user", "tenant").all()
        return TenantMembership.objects.select_related("user", "tenant").filter(tenant=tenant_for(self.request))

    def check_mutation_actor(self, tenant_id):
        if platform_context(self.request):
            return
        if not TenantMembership.objects.filter(user=self.request.user, tenant_id=tenant_id,
                role="owner", is_active=True, tenant__is_active=True, user__is_active=True).exists():
            raise PermissionDenied("An active owner membership is required.")

    def perform_create(self, serializer):
        tenant = serializer.validated_data["tenant"] if platform_context(self.request) else tenant_for(self.request)
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            self.check_mutation_actor(tenant.pk)
            audit(self.request, "tenant.member_added", serializer.save(tenant=tenant))

    def perform_update(self, serializer):
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=serializer.instance.tenant_id)
            self.check_mutation_actor(serializer.instance.tenant_id)
            serializer.instance = TenantMembership.objects.select_for_update().get(pk=serializer.instance.pk)
            for field in ("user", "tenant"):
                value = serializer.validated_data.get(field)
                if value and value.pk != getattr(serializer.instance, f"{field}_id"):
                    raise ValidationError({field: "Membership identity cannot be changed."})
            self.check_last_owner(serializer.instance, serializer.validated_data.get("role", serializer.instance.role), serializer.validated_data.get("is_active", serializer.instance.is_active))
            audit(self.request, "tenant.member_updated", serializer.save())

    def check_last_owner(self, membership, role, is_active=False):
        if membership.role == "owner" and membership.is_active and (role != "owner" or not is_active) and not TenantMembership.objects.filter(tenant_id=membership.tenant_id, role="owner", is_active=True, user__is_active=True).exclude(pk=membership.pk).exists():
            raise ValidationError("The final tenant owner cannot be removed.")

    def perform_destroy(self, instance):
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=instance.tenant_id)
            self.check_mutation_actor(instance.tenant_id)
            instance = TenantMembership.objects.select_for_update().get(pk=instance.pk)
            self.check_last_owner(instance, None)
            audit(self.request, "tenant.member_removed", instance)
            instance.delete()


class TenantSettingView(generics.RetrieveUpdateAPIView):
    serializer_class = TenantSettingSerializer
    permission_classes = [IsTenantManager]

    def get_object(self):
        settings, _ = TenantSetting.objects.get_or_create(
            tenant=tenant_for(self.request)
        )
        return settings

    def perform_update(self, serializer):
        with transaction.atomic():
            audit(self.request, "tenant.settings_updated", serializer.save())


class TenantProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsTenantManager]
    serializer_class = TenantProfileSerializer

    def get_object(self):
        return tenant_for(self.request)

    def perform_update(self, serializer):
        with transaction.atomic():
            audit(self.request, "tenant.profile_updated", serializer.save())
