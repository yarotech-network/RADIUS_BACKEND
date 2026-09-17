from datetime import datetime, time, timedelta
from django.conf import settings
from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from apps.core.api import tenant_for
from apps.core.pagination import StandardResultsPagination
from .device_access_sync import canonical_mac
from .models import DeviceAccessSession, DeviceAccessSync


class DeviceFilterSerializer(serializers.Serializer):
    voucher = serializers.IntegerField(required=False, min_value=1)
    period = serializers.ChoiceField(choices=["all", "today", "week", "month", "custom"], default="all")
    activity = serializers.ChoiceField(choices=["all", "online", "offline", "unknown"], default="all")
    search = serializers.CharField(max_length=64, required=False, allow_blank=True)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs["period"] == "custom":
            if not attrs.get("start") or not attrs.get("end") or attrs["start"] > attrs["end"]:
                raise serializers.ValidationError("Choose a valid start and end date.")
        return attrs


class DeviceUsageSerializer(serializers.Serializer):
    mac_address = serializers.CharField()
    codes_used = serializers.IntegerField()
    lifetime_codes_used = serializers.IntegerField()
    sessions = serializers.IntegerField()
    first_seen = serializers.DateTimeField()
    last_seen = serializers.DateTimeField()
    bytes_total = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["online", "offline", "unknown"])


class CodeUsageSerializer(serializers.Serializer):
    voucher_id = serializers.IntegerField()
    access_code = serializers.CharField()
    plan = serializers.CharField()
    status = serializers.CharField()
    expires_at = serializers.DateTimeField(allow_null=True)
    device_limit = serializers.IntegerField()
    first_seen = serializers.DateTimeField()
    last_seen = serializers.DateTimeField()
    sessions = serializers.IntegerField()
    bytes_total = serializers.IntegerField()


class CustomerDeviceViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    serializer_class = DeviceUsageSerializer
    http_method_names = ["get", "head", "options"]

    def context_data(self):
        tenant = tenant_for(self.request)
        validator = DeviceFilterSerializer(data=self.request.query_params)
        validator.is_valid(raise_exception=True)
        filters = validator.validated_data
        now = timezone.now()
        state = DeviceAccessSync.objects.filter(pk=1).first()
        fresh = bool(state and state.completed_at and state.completed_at >= now - timedelta(minutes=2))
        base = DeviceAccessSession.objects.filter(tenant=tenant, voucher__tenant=tenant)
        if filters.get("voucher"):
            base = base.filter(voucher_id=filters["voucher"])
        recent = Q(stopped_at__isnull=True, last_seen_at__gte=now - timedelta(minutes=5))
        if not fresh:
            recent &= Q(pk__isnull=True)
        # Status is current and independent of the chosen historical period.
        current = base.values("mac_address").annotate(open_count=Count("id", filter=Q(stopped_at__isnull=True)), recent_count=Count("id", filter=recent))
        activity = filters["activity"]
        if activity == "online":
            current = current.filter(recent_count__gt=0)
        elif activity == "offline":
            current = current.filter(open_count=0)
        elif activity == "unknown":
            current = current.filter(open_count__gt=0, recent_count=0)
        query = base.filter(mac_address__in=current.values("mac_address"))
        search = filters.get("search", "")
        if search:
            # Searches MACs only: avoid putting reusable access codes in URLs/logs.
            query = query.filter(mac_address__icontains=canonical_mac(search) or search)
        today = timezone.localdate(now)
        period = filters["period"]
        start = end = None
        if period == "today":
            start, end = today, today
        elif period == "week":
            start, end = today - timedelta(days=today.weekday()), today
        elif period == "month":
            start, end = today.replace(day=1), today
        elif period == "custom":
            start, end = filters["start"], filters["end"]
        if start:
            begin = timezone.make_aware(datetime.combine(start, time.min))
            finish = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
            query = query.filter(started_at__lt=finish, last_seen_at__gte=begin)
        return base, query, recent, state

    @extend_schema(parameters=[DeviceFilterSerializer])
    def list(self, request):
        base, query, recent, state = self.context_data()
        grouped = query.values("mac_address").annotate(codes_used=Count("voucher_id", distinct=True), sessions=Count("id"),
            first_seen=Min("started_at"), last_seen=Max("last_seen_at"), incoming=Sum("bytes_in"), outgoing=Sum("bytes_out")).order_by("-last_seen", "mac_address")
        page = self.paginate_queryset(grouped)
        macs = [item["mac_address"] for item in page]
        totals = {item["mac_address"]: item for item in base.filter(mac_address__in=macs).values("mac_address").annotate(
            lifetime=Count("voucher_id", distinct=True), opens=Count("id", filter=Q(stopped_at__isnull=True)), online=Count("id", filter=recent))}
        for item in page:
            total = totals[item["mac_address"]]
            item["lifetime_codes_used"] = total["lifetime"]
            item["status"] = "online" if total["online"] else "unknown" if total["opens"] else "offline"
            item["bytes_total"] = item.pop("incoming") + item.pop("outgoing")
        response = self.get_paginated_response(DeviceUsageSerializer(page, many=True).data)
        response.data.update(summary={"devices": grouped.count(), "distinct_codes": query.values("voucher_id").distinct().count()},
            synced_at=state.completed_at if state else None, timezone=settings.TIME_ZONE,
            accounting_note="Usage includes whole recorded sessions overlapping the selected period; online requires accounting within five minutes and a recent sync.")
        response["Cache-Control"] = "no-store"
        return response

    @extend_schema(parameters=[DeviceFilterSerializer])
    @action(detail=True, methods=["get"], serializer_class=CodeUsageSerializer)
    def codes(self, request, pk=None):
        mac = canonical_mac(pk)
        if not mac:
            raise ValidationError("Invalid MAC address.")
        base, query, recent, state = self.context_data()
        if not base.filter(mac_address=mac).exists():
            raise NotFound()
        grouped = query.filter(mac_address=mac).values("voucher_id", "voucher__username", "voucher__plan__name", "voucher__status", "voucher__expires_at", "voucher__device_limit").annotate(
            first_seen=Min("started_at"), last_seen=Max("last_seen_at"), sessions=Count("id"), incoming=Sum("bytes_in"), outgoing=Sum("bytes_out")).order_by("-last_seen", "voucher_id")
        membership = getattr(request.user, "membership", None)
        reveal = membership and membership.role in ("owner", "manager")
        now = timezone.now()
        results = []
        for item in self.paginate_queryset(grouped):
            expiry = item["voucher__expires_at"]
            status = item["voucher__status"]
            if status != "disabled" and expiry and expiry <= now:
                status = "expired"
            results.append(dict(voucher_id=item["voucher_id"], access_code=item["voucher__username"] if reveal else "Hidden",
                plan=item["voucher__plan__name"], status=status, expires_at=expiry, device_limit=item["voucher__device_limit"],
                first_seen=item["first_seen"], last_seen=item["last_seen"], sessions=item["sessions"], bytes_total=item["incoming"] + item["outgoing"]))
        response = self.get_paginated_response(CodeUsageSerializer(results, many=True).data)
        response["Cache-Control"] = "no-store"
        return response
