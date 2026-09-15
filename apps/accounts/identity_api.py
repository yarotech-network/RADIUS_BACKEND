from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from .identity import request_email_change, confirm_email_change
from .serializers import UserSerializer


class EmailChangeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class EmailChangeConfirmSerializer(serializers.Serializer):
    code = serializers.RegexField(r'^\d{6}$', write_only=True)


class EmailChangeView(APIView):
    serializer_class = EmailChangeSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'email_resend'

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        sent = request_email_change(request.user, **serializer.validated_data)
        return Response({'delivery_status': 'sent' if sent else 'failed',
                         'detail': 'Check your new email for a code.' if sent else 'Email delivery failed. Please retry.'},
                        status=200 if sent else 503)


class EmailChangeConfirmView(APIView):
    serializer_class = EmailChangeConfirmSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'email_verify'

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = confirm_email_change(request.user, **serializer.validated_data)
        return Response(UserSerializer(user).data)
