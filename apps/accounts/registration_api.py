from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.tenants.models import Tenant
from .registration import RegistrationError, request_code, verify_code, create_workspace


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class CodeSerializer(EmailSerializer):
    code = serializers.RegexField(r'^\d{6}$', write_only=True)


class WorkspaceSerializer(EmailSerializer):
    registration_token = serializers.CharField(max_length=150, write_only=True)
    workspace_id = serializers.RegexField(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', min_length=3, max_length=50)
    tenant_name = serializers.CharField(min_length=2, max_length=200)
    username = serializers.RegexField(r'^[\w.@+-]+$', min_length=3, max_length=150)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(min_length=10, max_length=20)
    password = serializers.CharField(min_length=8, write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_workspace_id(self, value):
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError('This workspace ID is already taken.')
        return value

    def validate_username(self, value):
        if get_user_model().objects.filter(username=value).exists():
            raise serializers.ValidationError('Username already taken.')
        return value

    def validate_email(self, value):
        if get_user_model().objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account already uses this email. Please sign in.')
        return value.lower()

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': "Passwords do not match."})
        user = get_user_model()(username=data['username'], email=data['email'], first_name=data['first_name'], last_name=data['last_name'])
        try:
            validate_password(data['password'], user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({'password': error.messages})
        return data


class RegistrationBaseView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response

    def handle_exception(self, exc):
        if isinstance(exc, RegistrationError):
            return Response({'detail': str(exc), 'code': exc.code}, status=exc.status)
        return super().handle_exception(exc)


class RegistrationEmailView(RegistrationBaseView):
    serializer_class = EmailSerializer
    throttle_scope = 'email_resend'

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_code(serializer.validated_data['email'])
        return Response({'message': 'If this email can be registered, a code is on its way. Already registered? Sign in.', 'resend_after': 60})


class RegistrationVerifyView(RegistrationBaseView):
    serializer_class = CodeSerializer
    throttle_scope = 'email_verify'

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = verify_code(**serializer.validated_data)
        return Response({'registration_token': token, 'expires_in': 1800})


class RegistrationCreateView(RegistrationBaseView):
    serializer_class = WorkspaceSerializer
    throttle_scope = 'login'

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user, tenant = create_workspace(serializer.validated_data)
        except IntegrityError:
            return Response({'detail': 'Email, username or workspace ID is already in use. Please check your details or sign in.'}, status=409)
        return Response({'workspace': {'name': tenant.name, 'slug': tenant.slug}, 'username': user.username}, status=201)
