from apps.subscriptions.entitlements import authorize_print, require_print_authorization
from apps.core.api import tenant_for
from rest_framework import viewsets, generics, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpResponse
from .models import Voucher, InternetPlan, PaymentTransaction
from .serializers import (
    VoucherSerializer, InternetPlanSerializer,
    VoucherGenerateSerializer, PaymentTransactionSerializer,
)
from .services import VoucherService
from .filters import VoucherFilter, PaymentTransactionFilter
from apps.core.permissions import IsTenantManager
from apps.core.commands import idempotent
from django.utils.html import escape
from apps.core.mixins import AuditedCrudMixin
from apps.core.api import audit
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import Radcheck


class InternetPlanViewSet(AuditedCrudMixin, viewsets.ModelViewSet):
    filterset_fields = ["is_active", "duration_hours"]
    search_fields = ["name"]
    ordering = ["price", "id"]
    serializer_class = InternetPlanSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return InternetPlan.objects.none()
        return InternetPlan.objects.filter(tenant=tenant_for(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for(self.request))

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]


class VoucherViewSet(AuditedCrudMixin, viewsets.ModelViewSet):
    serializer_class = VoucherSerializer
    filterset_class = VoucherFilter
    search_fields = ["username", "status"]
    ordering_fields = ["created_at", "status", "expires_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Voucher.objects.none()
        return Voucher.objects.filter(tenant=tenant_for(self.request)).select_related("plan", "tenant", "agent__user").order_by("-created_at", "-id")

    def get_permissions(self):
        if self.action in ["list", "retrieve", "print", "pdf", "authorize_print"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]

    def perform_create(self, serializer):
        voucher = serializer.save(
            tenant=tenant_for(self.request),
            generation_source="admin",
        )
        VoucherService.write_radius_credentials(voucher)

    def perform_update(self, serializer):
        voucher = Voucher.objects.select_for_update().get(pk=serializer.instance.pk)
        if voucher.status != "unused" or hasattr(voucher, "payment") or hasattr(voucher, "agent_allocation"):
            raise ValidationError("Issued or purchased vouchers cannot be edited; use disable instead.")
        old_username = voucher.username
        serializer.instance = voucher
        voucher = serializer.save()
        Radcheck.objects.filter(username=old_username).delete()
        VoucherService.write_radius_credentials(voucher)

    def perform_destroy(self, instance):
        voucher = Voucher.objects.select_for_update().get(pk=instance.pk)
        if voucher.status != "unused" or hasattr(voucher, "payment") or hasattr(voucher, "agent_allocation"):
            raise ValidationError("Issued or purchased vouchers cannot be deleted; use disable instead.")
        Radcheck.objects.filter(username=voucher.username).delete()
        voucher.delete()

    @action(detail=False, methods=["post"])
    @idempotent
    @transaction.atomic
    def generate(self, request):
        serializer = VoucherGenerateSerializer(
            data=request.data,
            context={"tenant": tenant_for(request)},
        )
        serializer.is_valid(raise_exception=True)

        vouchers = VoucherService.generate_vouchers(
            tenant=tenant_for(request),
            plan_id=serializer.validated_data["plan_id"],
            quantity=serializer.validated_data["quantity"],
            prefix=serializer.validated_data.get("prefix", ""),
            source="admin",
        )
        audit(request, "vouchers.generated", vouchers[0], {"quantity": len(vouchers), "plan_id": serializer.validated_data["plan_id"]})

        return Response(
            VoucherSerializer(vouchers, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    @idempotent
    @transaction.atomic
    def disable(self, request, pk=None):
        voucher = self.get_object()
        VoucherService.disable_voucher(voucher)
        audit(request, "voucher.disabled", voucher)
        return Response({"message": "Voucher disabled."})

    @action(detail=False, methods=["post"], url_path="authorize-print")
    def authorize_print(self, request):
        from rest_framework import serializers
        field = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=1000)
        ids = field.run_validation(request.data.get("voucher_ids"))
        return Response(authorize_print(tenant_for(request), ids))

    @action(detail=True, methods=["get"])
    def print(self, request, pk=None):
        voucher = self.get_object()
        require_print_authorization(voucher)
        html_string = f"""
        <html>
        <body>
        <h1>YAROTECH Voucher</h1>
        <p><strong>Username:</strong> {escape(voucher.username)}</p>
        <p><strong>Password:</strong> {escape(voucher.password)}</p>
        <p><strong>Plan:</strong> {escape(voucher.plan.name)}</p>
        <p><strong>Duration:</strong> {voucher.plan.duration_hours} hours</p>
        <p><strong>Status:</strong> {voucher.status}</p>
        </body>
        </html>
        """
        return HttpResponse(html_string, content_type="text/html", headers={"Cache-Control": "private, no-store"})

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        voucher = self.get_object()
        require_print_authorization(voucher)
        html_string = f"""
        <html>
        <body>
        <h1>YAROTECH Voucher</h1>
        <p><strong>Username:</strong> {escape(voucher.username)}</p>
        <p><strong>Password:</strong> {escape(voucher.password)}</p>
        <p><strong>Plan:</strong> {escape(voucher.plan.name)}</p>
        <p><strong>Duration:</strong> {voucher.plan.duration_hours} hours</p>
        <p><strong>Status:</strong> {voucher.status}</p>
        </body>
        </html>
        """
        try:
            from weasyprint import HTML
            pdf = HTML(string=html_string).write_pdf()
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="voucher_{voucher.pk}.pdf"'
            response["Cache-Control"] = "private, no-store"
            return response
        except (ImportError, OSError):
            return Response({"error": "PDF generation is unavailable. Use the print endpoint."}, status=503)


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentTransactionSerializer
    filterset_class = PaymentTransactionFilter

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PaymentTransaction.objects.none()
        return PaymentTransaction.objects.filter(tenant=tenant_for(self.request))
