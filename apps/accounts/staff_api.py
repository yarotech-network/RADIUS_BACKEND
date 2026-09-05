import hashlib
import secrets
from datetime import timedelta
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework.permissions import AllowAny
from django.utils import timezone
from rest_framework import serializers, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from apps.core.permissions import IsPlatformAdmin
from apps.core.api import audit
from .staff_models import StaffAssignment, StaffInvitation
from drf_spectacular.utils import extend_schema

SERVICES = ["routers.view", "routers.test", "live_sessions.view", "live_sessions.disconnect", "payments.view", "payments.support", "vouchers.generate", "vouchers.print"]


class StaffAssignmentSerializer(serializers.ModelSerializer):
    services = serializers.ListField(child=serializers.ChoiceField(choices=SERVICES), max_length=len(SERVICES))
    class Meta:
        model = StaffAssignment
        fields = ["id", "user", "tenant", "services", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        user = data.get("user", getattr(self.instance, "user", None))
        if user and (user.is_platform_admin or hasattr(user, "membership") or hasattr(user, "agent_profile")):
            raise ValidationError("Staff assignments require a dedicated staff account.")
        if self.instance and any(k in data and data[k].pk != getattr(self.instance, f"{k}_id") for k in ("user", "tenant")):
            raise ValidationError("Assignment identity cannot be changed; revoke and create a new assignment.")
        return data


class StaffAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = StaffAssignmentSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = StaffAssignment.objects.select_related("user", "tenant").order_by("id")
    filterset_fields = ["user", "tenant", "is_active"]

    def perform_create(self, serializer):
        with transaction.atomic():
            assignment = serializer.save()
            audit(self.request, "staff.assignment_created", assignment)

    def perform_update(self, serializer):
        with transaction.atomic():
            assignment = serializer.save()
            audit(self.request, "staff.assignment_updated", assignment)

    def perform_destroy(self, instance):
        with transaction.atomic():
            audit(self.request, "staff.assignment_revoked", instance)
            instance.delete()


class StaffInvitationSerializer(serializers.ModelSerializer):
    services = serializers.ListField(child=serializers.ChoiceField(choices=SERVICES), max_length=len(SERVICES))
    class Meta:
        model = StaffInvitation
        fields = ["id", "email", "tenant", "services", "expires_at", "status", "created_at"]
        read_only_fields = ["id", "expires_at", "status", "created_at"]


class CreatedStaffInvitationSerializer(StaffInvitationSerializer):
    token = serializers.CharField(read_only=True)
    class Meta(StaffInvitationSerializer.Meta):
        fields = [*StaffInvitationSerializer.Meta.fields, "token"]


class StaffInvitationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = StaffInvitationSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = StaffInvitation.objects.order_by("-created_at", "id")
    filterset_fields = ["tenant", "status"]

    @extend_schema(request=StaffInvitationSerializer, responses={201: CreatedStaffInvitationSerializer})
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = secrets.token_urlsafe(32)
        with transaction.atomic():
            invitation = serializer.save(token_digest=hashlib.sha256(token.encode()).hexdigest(), expires_at=timezone.now() + timedelta(days=3))
            audit(request, "staff.invited", invitation)
        return Response({**self.get_serializer(invitation).data, "token": token}, status=201, headers={"Cache-Control": "no-store"})

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        invitation = self.get_object()
        with transaction.atomic():
            invitation = StaffInvitation.objects.select_for_update().get(pk=invitation.pk)
            if invitation.status == "pending":
                invitation.status = "revoked"
                invitation.save(update_fields=["status"])
                audit(request, "staff.invitation_revoked", invitation)
        return Response(self.get_serializer(invitation).data)


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128, write_only=True)
    username = serializers.CharField(max_length=150, min_length=3, required=False)
    password = serializers.CharField(write_only=True, trim_whitespace=False, required=False)


class MyStaffAssignmentsViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = StaffAssignmentSerializer
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StaffAssignment.objects.none()
        return StaffAssignment.objects.filter(user=self.request.user, is_active=True, tenant__is_active=True).order_by("id")


class AcceptStaffInvitationView(APIView):
    serializer_class = AcceptInvitationSerializer
    permission_classes = [AllowAny]

    @extend_schema(request=AcceptInvitationSerializer, responses=StaffAssignmentSerializer)
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        digest = hashlib.sha256(serializer.validated_data["token"].encode()).hexdigest()
        with transaction.atomic():
            invitation = StaffInvitation.objects.select_for_update().filter(token_digest=digest).first()
            if invitation is None or invitation.status != "pending" or invitation.expires_at <= timezone.now():
                raise ValidationError("Invitation is invalid or expired.")
            if not invitation.tenant.is_active:
                raise ValidationError("Tenant is inactive.")
            user = request.user
            if not user.is_authenticated:
                User = get_user_model()
                if User.objects.filter(email__iexact=invitation.email).exists():
                    raise ValidationError("Sign in with the invited account.")
                username = serializer.validated_data.get("username")
                password = serializer.validated_data.get("password")
                if not username or not password:
                    raise ValidationError("Username and password are required for a new account.")
                if User.objects.filter(username=username).exists():
                    raise ValidationError({"username": "Username already taken."})
                candidate = User(username=username, email=invitation.email)
                validate_password(password, candidate)
                user = User.objects.create_user(username=username, email=invitation.email, password=password)
            elif invitation.email.casefold() != user.email.casefold():
                raise ValidationError("Sign in with the invited account.")
            values = {"user": user.pk, "tenant": invitation.tenant_id, "services": invitation.services, "is_active": True}
            existing = StaffAssignment.objects.filter(user=user, tenant=invitation.tenant).first()
            assignment_serializer = StaffAssignmentSerializer(existing, data=values)
            assignment_serializer.is_valid(raise_exception=True)
            assignment = assignment_serializer.save()
            invitation.status = "accepted"
            invitation.save(update_fields=["status"])
            from apps.core.models import AuditEvent
            AuditEvent.objects.create(actor=user, tenant=invitation.tenant, action="staff.invitation_accepted", resource=f"accounts.staffassignment:{assignment.pk}")
        return Response(StaffAssignmentSerializer(assignment).data)
