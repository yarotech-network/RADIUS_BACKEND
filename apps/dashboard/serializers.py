from rest_framework import serializers


class DashboardStatsSerializer(serializers.Serializer):
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
