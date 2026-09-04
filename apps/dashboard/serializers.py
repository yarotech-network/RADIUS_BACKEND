from rest_framework import serializers


class DashboardStatsSerializer(serializers.Serializer):
    total_vouchers = serializers.IntegerField()
    active_vouchers = serializers.IntegerField()
    total_revenue = serializers.IntegerField()
    total_agents = serializers.IntegerField()
    total_routers = serializers.IntegerField()
    active_routers = serializers.IntegerField()


class LiveUserSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    username = serializers.CharField()
    ip_address = serializers.IPAddressField()
    client_ip = serializers.IPAddressField(allow_null=True)
    session_time = serializers.IntegerField()
    bytes_in = serializers.IntegerField()
    bytes_out = serializers.IntegerField()
    connected_at = serializers.DateTimeField(allow_null=True)


class LiveUsersResponseSerializer(serializers.Serializer):
    users = LiveUserSerializer(many=True)
    count = serializers.IntegerField()


class DisconnectSessionResponseSerializer(serializers.Serializer):
    acknowledged = serializers.BooleanField()
