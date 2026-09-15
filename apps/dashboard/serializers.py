from rest_framework import serializers


class DashboardStatsSerializer(serializers.Serializer):
    collected_revenue = serializers.DictField(child=serializers.IntegerField())
    revenue_sources = serializers.DictField(child=serializers.IntegerField())
    voucher_usage = serializers.DictField(child=serializers.IntegerField())
    vouchers_issued_today = serializers.IntegerField()
    successful_payments = serializers.IntegerField()
    failed_payments = serializers.IntegerField()
    active_plans = serializers.IntegerField()
    total_plans = serializers.IntegerField()
    reporting_timezone = serializers.CharField()
    total_vouchers = serializers.IntegerField()
    active_vouchers = serializers.IntegerField()
    total_revenue = serializers.IntegerField()
    total_agents = serializers.IntegerField()
    total_routers = serializers.IntegerField()
    active_routers = serializers.IntegerField()
    currency = serializers.CharField()
    amount_unit = serializers.CharField()
    observed_at = serializers.DateTimeField()
    pending_payments = serializers.IntegerField()
    paid_unfulfilled_payments = serializers.IntegerField()


class LiveUserSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    username = serializers.CharField()
    ip_address = serializers.IPAddressField()
    client_ip = serializers.IPAddressField(allow_null=True)
    session_time = serializers.IntegerField()
    bytes_in = serializers.IntegerField()
    bytes_out = serializers.IntegerField()
    connected_at = serializers.DateTimeField(allow_null=True)
    router_id = serializers.UUIDField(allow_null=True)
    router_name = serializers.CharField(allow_null=True)


class LiveUsersResponseSerializer(serializers.Serializer):
    users = LiveUserSerializer(many=True)
    count = serializers.IntegerField()
    current_page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    observed_at = serializers.DateTimeField()
    source = serializers.CharField()


class DisconnectSessionResponseSerializer(serializers.Serializer):
    acknowledged = serializers.BooleanField()


class NetworkRouterSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=['online', 'offline', 'unknown', 'awaiting_import', 'inactive'])
    online_users = serializers.IntegerField()
    last_seen_at = serializers.DateTimeField(allow_null=True)


class NetworkSummarySerializer(serializers.Serializer):
    rate_sampled_sessions = serializers.IntegerField()
    online_users = serializers.IntegerField()
    online_vouchers = serializers.IntegerField()
    stale_sessions = serializers.IntegerField()
    sessions_today = serializers.IntegerField()
    live_upload_bytes = serializers.IntegerField()
    live_download_bytes = serializers.IntegerField()
    live_traffic_bytes = serializers.IntegerField()
    today_upload_bytes = serializers.IntegerField()
    today_download_bytes = serializers.IntegerField()
    today_traffic_bytes = serializers.IntegerField()
    all_time_upload_bytes = serializers.IntegerField()
    all_time_download_bytes = serializers.IntegerField()
    all_time_traffic_bytes = serializers.IntegerField()
    upload_bytes_per_second = serializers.IntegerField(allow_null=True)
    download_bytes_per_second = serializers.IntegerField(allow_null=True)
    latest_accounting_at = serializers.DateTimeField(allow_null=True)
    router_counts = serializers.DictField(child=serializers.IntegerField())
    routers = NetworkRouterSerializer(many=True)
    routers_total = serializers.IntegerField()
    observed_at = serializers.DateTimeField()
    freshness_seconds = serializers.IntegerField()
    traffic_basis = serializers.CharField()
    source = serializers.CharField()
