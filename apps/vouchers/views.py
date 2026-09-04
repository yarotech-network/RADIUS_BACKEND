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


class InternetPlanViewSet(viewsets.ModelViewSet):
    serializer_class = InternetPlanSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return InternetPlan.objects.none()
        return InternetPlan.objects.filter(tenant=self.request.user.membership.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.membership.tenant)

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]


class VoucherViewSet(viewsets.ModelViewSet):
    serializer_class = VoucherSerializer
    filterset_class = VoucherFilter
    search_fields = ["username", "status"]
    ordering_fields = ["created_at", "status", "expires_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Voucher.objects.none()
        return Voucher.objects.filter(tenant=self.request.user.membership.tenant)

    def get_permissions(self):
        if self.action in ["list", "retrieve", "print", "pdf"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.membership.tenant,
            generation_source="admin",
        )

    @action(detail=False, methods=["post"])
    def generate(self, request):
        serializer = VoucherGenerateSerializer(
            data=request.data,
            context={"tenant": request.user.membership.tenant},
        )
        serializer.is_valid(raise_exception=True)

        vouchers = VoucherService.generate_vouchers(
            tenant=request.user.membership.tenant,
            plan_id=serializer.validated_data["plan_id"],
            quantity=serializer.validated_data["quantity"],
            prefix=serializer.validated_data.get("prefix", ""),
            source="admin",
        )

        return Response(
            VoucherSerializer(vouchers, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None):
        voucher = self.get_object()
        VoucherService.disable_voucher(voucher)
        return Response({"message": "Voucher disabled."})

    @action(detail=True, methods=["get"])
    def print(self, request, pk=None):
        voucher = self.get_object()
        html_string = f"""
        <html>
        <body>
        <h1>YAROTECH Voucher</h1>
        <p><strong>Username:</strong> {voucher.username}</p>
        <p><strong>Password:</strong> {voucher.password}</p>
        <p><strong>Plan:</strong> {voucher.plan.name}</p>
        <p><strong>Duration:</strong> {voucher.plan.duration_hours} hours</p>
        <p><strong>Status:</strong> {voucher.status}</p>
        </body>
        </html>
        """
        return HttpResponse(html_string, content_type="text/html")

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        voucher = self.get_object()
        html_string = f"""
        <html>
        <body>
        <h1>YAROTECH Voucher</h1>
        <p><strong>Username:</strong> {voucher.username}</p>
        <p><strong>Password:</strong> {voucher.password}</p>
        <p><strong>Plan:</strong> {voucher.plan.name}</p>
        <p><strong>Duration:</strong> {voucher.plan.duration_hours} hours</p>
        <p><strong>Status:</strong> {voucher.status}</p>
        </body>
        </html>
        """
        try:
            from weasyprint import HTML
            pdf = HTML(string=html_string).write_pdf()
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="voucher_{voucher.username}.pdf"'
            return response
        except ImportError:
            return HttpResponse(html_string, content_type="text/html")


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentTransactionSerializer
    filterset_class = PaymentTransactionFilter

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PaymentTransaction.objects.none()
        return PaymentTransaction.objects.filter(tenant=self.request.user.membership.tenant)
