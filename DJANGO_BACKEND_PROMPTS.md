# YAROTECH RADIUS SYSTEM — Django REST Framework Backend Prompts

> **Purpose:** This file contains 15 detailed, step-by-step prompts to rebuild the entire YAROTECH RADIUS SYSTEM backend using **Django 5.1** + **Django REST Framework (DRF)** + **SimpleJWT** for authentication + **PostgreSQL**. Each prompt includes exact file paths, full file contents, and all necessary commands. Every model, serializer, viewset, URL, and service from the original system is covered.

---

## Table of Contents

1. [Project Scaffolding, Settings & Dependencies](#prompt-1-project-scaffolding-settings--dependencies)
2. [Custom User Model & JWT Authentication](#prompt-2-custom-user-model--jwt-authentication)
3. [Tenant Models, Serializers & ViewSets](#prompt-3-tenant-models-serializers--viewsets)
4. [Internet Plan & Voucher Models](#prompt-4-internet-plan--voucher-models)
5. [Voucher Services & RADIUS Integration](#prompt-5-voucher-services--radius-integration)
6. [Voucher API Endpoints](#prompt-6-voucher-api-endpoints)
7. [Payment & Paystack Integration](#prompt-7-payment--paystack-integration)
8. [Router Models & State Machine](#prompt-8-router-models--state-machine)
9. [Router Provisioning & WireGuard](#prompt-9-router-provisioning--wireguard)
10. [Router API Endpoints](#prompt-10-router-api-endpoints)
11. [Agent Models & Wallet System](#prompt-11-agent-models--wallet-system)
12. [Agent API Endpoints](#prompt-12-agent-api-endpoints)
13. [Subscription & Billing](#prompt-13-subscription--billing)
14. [WhatsApp Integration](#prompt-14-whatsapp-integration)
15. [MAC Devices, Admin & Management Commands](#prompt-15-mac-devices-admin--management-commands)

---

## Prompt 1: Project Scaffolding, Settings & Dependencies

### Commands to Run
```bash
# Create project directory
mkdir yarotech-radius-backend
cd yarotech-radius-backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # Linux/Mac

# Install dependencies
pip install django==5.1 djangorestframework djangorestframework-simplejwt
pip install psycopg2-binary python-decouple django-cors-headers
pip install django-filter drf-spectacular drf-spectacular[sidecar]
pip install requests qrcode Pillow cryptography pyotp
pip install weasyprint fpdf2
pip install pytest pytest-django
pip freeze > requirements.txt

# Create Django project
django-admin startproject config .
python manage.py startapp accounts
python manage.py startapp tenants
python manage.py startapp vouchers
python manage.py startapp routers
python manage.py startapp agents
python manage.py startapp payments
python manage.py startapp subscriptions
python manage.py startapp whatsapp_routing
python manage.py startapp iot_devices
python manage.py startapp dashboard
```

### Folder Structure
```
yarotech-radius-backend/
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── accounts/                  # Custom user, JWT auth
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── permissions.py
│   └── backends.py
├── tenants/                   # Multi-tenant models
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── middleware.py
├── vouchers/                  # Voucher generation, RADIUS
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── services.py
│   ├── filters.py
│   └── management/commands/
│       ├── expire_vouchers.py
│       └── sync_vouchers.py
├── routers/                   # Router onboarding, provisioning
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── services.py
│   ├── state_machine.py
│   ├── provisioners.py
│   ├── secret_store.py
│   └── management/commands/
│       └── refresh_router_statuses.py
├── agents/                    # Agent portal, wallet
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── services.py
├── payments/                  # Paystack integration
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── services.py
│   └── webhooks.py
├── subscriptions/             # Subscription billing
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── whatsapp_routing/          # WhatsApp integration
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── iot_devices/               # MAC device management
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── dashboard/                 # Dashboard stats
│   ├── views.py
│   └── urls.py
├── core/                      # Shared utilities
│   ├── pagination.py
│   ├── permissions.py
│   ├── exceptions.py
│   └── utils.py
├── manage.py
├── requirements.txt
└── .env
```

### File: `config/settings.py`
```python
import os
from pathlib import Path
from decouple import config, Csv
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="change-me-in-production")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # Local apps
    "accounts",
    "tenants",
    "vouchers",
    "routers",
    "agents",
    "payments",
    "subscriptions",
    "whatsapp_routing",
    "iot_devices",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "tenants.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="yarotech_radius"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# === REST Framework ===
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# === SimpleJWT ===
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# === CORS ===
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# === DRF Spectacular ===
SPECTACULAR_SETTINGS = {
    "TITLE": "YAROTECH RADIUS API",
    "DESCRIPTION": "Multi-tenant RADIUS hotspot management API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# === Paystack ===
PAYSTACK_SECRET_KEY = config("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_PUBLIC_KEY = config("PAYSTACK_PUBLIC_KEY", default="")

# === WireGuard ===
WG_VPS_HOST = config("WG_VPS_HOST", default="")
WG_VPS_SSH_KEY = config("WG_VPS_SSH_KEY", default="")
WG_MANAGED_SUBNET = "10.100.100.0/24"

# === Provisioning Agent ===
ROUTER_PROVISIONING_AGENT_KEYS = config(
    "ROUTER_PROVISIONING_AGENT_KEYS", default="", cast=Csv()
)
ROUTER_PROVISIONING_AGENT_ALLOWED_NETWORKS = config(
    "ROUTER_PROVISIONING_AGENT_ALLOWED_NETWORKS", default="127.0.0.1", cast=Csv()
)

# === WhatsApp ===
WHATSAPP_API_VERSION = config("WHATSAPP_API_VERSION", default="v18.0")
WHATSAPP_APP_SECRET = config("WHATSAPP_APP_SECRET", default="")

# === Encryption ===
FERNET_KEY = config("FERNET_KEY", default="")

# === Email ===
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
```

### File: `config/urls.py`
```python
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # API v1
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("tenants.urls")),
    path("api/v1/", include("vouchers.urls")),
    path("api/v1/", include("routers.urls")),
    path("api/v1/", include("agents.urls")),
    path("api/v1/", include("payments.urls")),
    path("api/v1/", include("subscriptions.urls")),
    path("api/v1/", include("whatsapp_routing.urls")),
    path("api/v1/", include("iot_devices.urls")),
    path("api/v1/", include("dashboard.urls")),
    # API schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema")),
]
```

### File: `core/pagination.py`
```python
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "total_pages": self.page.paginator.num_pages,
            "current_page": self.page.number,
            "results": data,
        })
```

### File: `core/permissions.py`
```python
from rest_framework.permissions import BasePermission


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, "membership")
            and request.user.membership.role == "owner"
            and request.user.membership.tenant.is_platform_admin
        )


class IsTenantOwner(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, "membership")
            and request.user.membership.role == "owner"
        )


class IsTenantManager(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, "membership")
            and request.user.membership.role in ("owner", "manager")
        )


class IsAgent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, "agent_profile")
        )
```

### File: `.env`
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
DB_NAME=yarotech_radius
DB_USER=postgres
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173
PAYSTACK_SECRET_KEY=sk_test_xxxxx
PAYSTACK_PUBLIC_KEY=pk_test_xxxxx
FERNET_KEY=your-fernet-key-here
```

### Commands to Run
```bash
# Create database (PostgreSQL)
createdb yarotech_radius

# Run migrations
python manage.py makemigrations accounts tenants vouchers routers agents payments subscriptions whatsapp_routing iot_devices dashboard
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start dev server
python manage.py runserver
```

### Verify
```bash
# API docs should be accessible
python manage.py runserver
# Visit http://localhost:8000/api/docs/
```

---

## Prompt 2: Custom User Model & JWT Authentication

### What to Build
Custom User model with JWT authentication (login, register, refresh, password reset), role-based permissions.

### File: `accounts/models.py`
```python
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with role support."""

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    is_platform_admin = models.BooleanField(default=False)

    class Meta:
        db_table = "accounts_user"

    def __str__(self):
        return self.username

    @property
    def role(self):
        if self.is_platform_admin:
            return "platform_admin"
        if hasattr(self, "membership"):
            return self.membership.role
        if hasattr(self, "agent_profile"):
            return "agent"
        return "user"
```

### File: `accounts/serializers.py`
```python
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from tenants.models import Tenant, TenantMembership

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(read_only=True)
    tenant_name = serializers.CharField(source="membership.tenant.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "phone", "role", "tenant_name"]
        read_only_fields = ["id", "role", "tenant_name"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=3)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    tenant_name = serializers.CharField(min_length=2)
    phone = serializers.CharField(min_length=10)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords don't match."})
        return data

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            phone=validated_data.get("phone", ""),
        )
        tenant = Tenant.objects.create(
            name=validated_data["tenant_name"],
            slug=validated_data["tenant_name"].lower().replace(" ", "-"),
            phone=validated_data.get("phone", ""),
            email=validated_data["email"],
        )
        TenantMembership.objects.create(
            user=user,
            tenant=tenant,
            role="owner",
        )
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(min_length=8)
    password_confirm = serializers.CharField()

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords don't match."})
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
```

### File: `accounts/views.py`
```python
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import (
    UserSerializer, LoginSerializer, RegisterSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ChangePasswordSerializer,
)

User = get_user_model()


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(username=serializer.validated_data["username"]).first()
        if user and user.check_password(serializer.validated_data["password"]):
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            })
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"message": "Password changed successfully."})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # TODO: Send reset email with token
        return Response({"message": "Password reset email sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # TODO: Verify token and reset password
        return Response({"message": "Password reset successful."})
```

### File: `accounts/urls.py`
```python
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/user/", views.CurrentUserView.as_view(), name="current-user"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="change-password"),
    path("auth/password-reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
```

### Commands to Run
```bash
python manage.py makemigrations accounts
python manage.py migrate
python manage.py runserver
# Test: POST http://localhost:8000/api/v1/auth/register/
```

---

## Prompt 3: Tenant Models, Serializers & ViewSets

### What to Build
Multi-tenant models (Tenant, TenantMembership, TenantSetting), serializers, API viewsets with tenant-scoped filtering.

### File: `tenants/models.py`
```python
from django.db import models
from django.conf import settings


class Tenant(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_platform_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_tenant"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("manager", "Manager"),
        ("staff", "Staff"),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="staff")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenants_membership"
        unique_together = ["user", "tenant"]

    def __str__(self):
        return f"{self.user.username} -> {self.tenant.name} ({self.role})"


class TenantSetting(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="settings")
    paystack_secret_key = models.CharField(max_length=255, blank=True)
    paystack_public_key = models.CharField(max_length=255, blank=True)
    agent_commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    voucher_prefix = models.CharField(max_length=10, blank=True)
    max_funding_amount = models.PositiveIntegerField(default=100000)  # in kobo
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_setting"

    def __str__(self):
        return f"Settings for {self.tenant.name}"
```

### File: `tenants/serializers.py`
```python
from rest_framework import serializers
from .models import Tenant, TenantMembership, TenantSetting


class TenantSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, default=0)
    voucher_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tenant
        fields = [
            "id", "name", "slug", "phone", "email", "address",
            "is_active", "is_platform_admin", "created_at", "updated_at",
            "member_count", "voucher_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenantMembershipSerializer(serializers.ModelSerializer):
    user_display = serializers.CharField(source="user.username", read_only=True)
    tenant_display = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = TenantMembership
        fields = ["id", "user", "tenant", "role", "user_display", "tenant_display", "created_at"]
        read_only_fields = ["id", "created_at"]


class TenantSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSetting
        fields = [
            "id", "tenant", "paystack_secret_key", "paystack_public_key",
            "agent_commission_percent", "voucher_prefix", "max_funding_amount",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]
        extra_kwargs = {
            "paystack_secret_key": {"write_only": True},
            "paystack_public_key": {"write_only": True},
        }
```

### File: `tenants/middleware.py`
```python
class TenantMiddleware:
    """Attach tenant to request based on authenticated user's membership."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        if hasattr(request, "user") and request.user.is_authenticated:
            if hasattr(request.user, "membership"):
                request.tenant = request.user.membership.tenant
        response = self.get_response(request)
        return response
```

### File: `tenants/views.py`
```python
from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from django.db.models import Count
from .models import Tenant, TenantMembership, TenantSetting
from .serializers import TenantSerializer, TenantMembershipSerializer, TenantSettingSerializer
from core.permissions import IsPlatformAdmin


class TenantViewSet(viewsets.ModelViewSet):
    """Platform admins see all tenants; owners see their own."""
    serializer_class = TenantSerializer

    def get_queryset(self):
        if self.request.user.is_platform_admin:
            return Tenant.objects.annotate(
                member_count=Count("memberships"),
                voucher_count=Count("vouchers"),
            )
        return Tenant.objects.filter(
            memberships__user=self.request.user
        ).annotate(
            member_count=Count("memberships"),
            voucher_count=Count("vouchers"),
        )

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsPlatformAdmin()]


class TenantMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = TenantMembershipSerializer

    def get_queryset(self):
        if self.request.user.is_platform_admin:
            return TenantMembership.objects.all()
        return TenantMembership.objects.filter(tenant=self.request.user.membership.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.membership.tenant)


class TenantSettingView(generics.RetrieveUpdateAPIView):
    serializer_class = TenantSettingSerializer

    def get_object(self):
        settings, _ = TenantSetting.objects.get_or_create(
            tenant=self.request.user.membership.tenant
        )
        return settings
```

### File: `tenants/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("tenants", views.TenantViewSet, basename="tenant")
router.register("tenant-memberships", views.TenantMembershipViewSet, basename="tenant-membership")

urlpatterns = [
    path("", include(router.urls)),
    path("tenants/settings/", views.TenantSettingView.as_view(), name="tenant-settings"),
]
```

### Commands to Run
```bash
python manage.py makemigrations tenants
python manage.py migrate
```

---

## Prompt 4: Internet Plan & Voucher Models

### What to Build
InternetPlan and Voucher models with full lifecycle, RADIUS table models (radcheck, radreply, radacct).

### File: `vouchers/models.py`
```python
from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets
import string


class InternetPlan(models.Model):
    name = models.CharField(max_length=100)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="plans")
    price = models.PositiveIntegerField(help_text="Price in kobo")
    duration_hours = models.PositiveIntegerField(help_text="Access duration in hours")
    rate_limit = models.CharField(max_length=20, help_text="e.g., 5M/10M (up/down)")
    data_limit = models.PositiveIntegerField(default=0, help_text="Data limit in MB, 0=unlimited")
    voucher_prefix = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vouchers_internetplan"
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} - {self.get_price_display()}"

    def get_price_display(self):
        return f"₦{self.price / 100:,.0f}"


class Voucher(models.Model):
    STATUS_CHOICES = [
        ("unused", "Unused"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("disabled", "Disabled"),
    ]
    SOURCE_CHOICES = [
        ("admin", "Admin"),
        ("agent", "Agent"),
        ("customer", "Customer"),
    ]

    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=50)
    plan = models.ForeignKey(InternetPlan, on_delete=models.PROTECT, related_name="vouchers")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="vouchers")
    agent = models.ForeignKey("agents.AgentProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="unused")
    generation_source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="admin")
    device_limit = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vouchers_voucher"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.username} ({self.status})"

    @staticmethod
    def generate_credentials(prefix=""):
        alphabet = string.ascii_letters + string.digits
        username = prefix + "".join(secrets.choice(alphabet) for _ in range(8))
        password = "".join(secrets.choice(alphabet) for _ in range(12))
        return username, password

    def activate(self):
        self.status = "active"
        self.activated_at = timezone.now()
        self.expires_at = timezone.now() + timezone.timedelta(hours=self.plan.duration_hours)
        self.save(update_fields=["status", "activated_at", "expires_at"])

    def expire(self):
        self.status = "expired"
        self.save(update_fields=["status"])


class PaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("abandoned", "Abandoned"),
    ]

    reference = models.CharField(max_length=100, unique=True)
    amount = models.PositiveIntegerField(help_text="Amount in kobo")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    voucher = models.OneToOneField(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name="payment")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey(InternetPlan, on_delete=models.SET_NULL, null=True, blank=True)
    paystack_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vouchers_paymenttransaction"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.get_status_display()}"


# === FreeRADIUS SQL Tables (read-only in Django) ===

class Radcheck(models.Model):
    username = models.CharField(max_length=64, primary_key=True)
    attribute = models.CharField(max_length=64)
    op = models.CharField(max_length=2)
    value = models.CharField(max_length=253)

    class Meta:
        db_table = "radcheck"
        managed = False  # Django won't create/modify this table


class Radreply(models.Model):
    username = models.CharField(max_length=64)
    attribute = models.CharField(max_length=64)
    op = models.CharField(max_length=2)
    value = models.CharField(max_length=253)

    class Meta:
        db_table = "radreply"
        managed = False


class Radacct(models.Model):
    radacctid = models.BigAutoField(primary_key=True)
    sessionid = models.CharField(max_length=64)
    username = models.CharField(max_length=64)
    nasipaddress = models.GenericIPAddressField()
    nasportid = models.CharField(max_length=32, null=True)
    acctstarttime = models.DateTimeField(null=True)
    acctstoptime = models.DateTimeField(null=True)
    acctinputoctets = models.BigIntegerField(default=0)
    acctoutputoctets = models.BigIntegerField(default=0)
    acctsessiontime = models.IntegerField(default=0)
    acctterminatecause = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = "radacct"
        managed = False


class Radpostauth(models.Model):
    username = models.CharField(max_length=64)
    pass_reply = models.CharField(max_length=64)
    authdate = models.DateTimeField()

    class Meta:
        db_table = "radpostauth"
        managed = False
```

### File: `vouchers/serializers.py`
```python
from rest_framework import serializers
from .models import InternetPlan, Voucher, PaymentTransaction


class InternetPlanSerializer(serializers.ModelSerializer):
    price_display = serializers.CharField(source="get_price_display", read_only=True)

    class Meta:
        model = InternetPlan
        fields = [
            "id", "name", "price", "price_display", "duration_hours",
            "rate_limit", "data_limit", "voucher_prefix", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class VoucherSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    plan_duration = serializers.CharField(source="plan.duration_hours", read_only=True)
    price_display = serializers.CharField(source="plan.get_price_display", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    agent_name = serializers.CharField(source="agent.user.username", read_only=True, default=None)

    class Meta:
        model = Voucher
        fields = [
            "id", "username", "password", "plan", "plan_name", "plan_duration",
            "price_display", "tenant", "tenant_name", "agent", "agent_name",
            "status", "generation_source", "device_limit", "expires_at",
            "activated_at", "created_at",
        ]
        read_only_fields = ["id", "status", "expires_at", "activated_at", "created_at"]
        extra_kwargs = {
            "password": {"write_only": True},
        }


class VoucherGenerateSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    prefix = serializers.CharField(max_length=10, required=False, default="")

    def validate_plan_id(self, value):
        if not InternetPlan.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Plan not found or inactive.")
        return value


class PaymentTransactionSerializer(serializers.ModelSerializer):
    voucher_username = serializers.CharField(source="voucher.username", read_only=True, default=None)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id", "reference", "amount", "status", "customer_email",
            "customer_name", "customer_phone", "voucher", "voucher_username",
            "tenant", "plan", "paystack_reference", "created_at", "paid_at",
        ]
        read_only_fields = ["id", "status", "created_at", "paid_at"]
```

### Commands to Run
```bash
python manage.py makemigrations vouchers
python manage.py migrate
```

---

## Prompt 5: Voucher Services & RADIUS Integration

### What to Build
Core business logic: voucher generation with RADIUS row creation, payment processing, expiry management.

### File: `vouchers/services.py`
```python
from django.db import transaction
from django.utils import timezone
from .models import Voucher, InternetPlan, PaymentTransaction, Radcheck
import secrets
import string
import hashlib
import requests


class VoucherService:
    """Core voucher operations."""

    @staticmethod
    @transaction.atomic
    def generate_vouchers(tenant, plan_id, quantity, prefix="", agent=None, source="admin"):
        """Generate vouchers and create RADIUS radcheck rows."""
        plan = InternetPlan.objects.get(id=plan_id, tenant=tenant, is_active=True)
        vouchers = []

        for _ in range(quantity):
            username, password = Voucher.generate_credentials(prefix)

            # Ensure unique username
            while Voucher.objects.filter(username=username).exists():
                username, password = Voucher.generate_credentials(prefix)

            voucher = Voucher.objects.create(
                username=username,
                password=password,
                plan=plan,
                tenant=tenant,
                agent=agent,
                generation_source=source,
                device_limit=1,
            )

            # Create radcheck rows for FreeRADIUS
            Radcheck.objects.create(
                username=username,
                attribute="Cleartext-Password",
                op:=":=",
                value=password,
            )
            Radcheck.objects.create(
                username=username,
                attribute="Max-Days",
                op:=":=",
                value=str(plan.duration_hours * 3600),  # Convert to seconds
            )
            if plan.data_limit > 0:
                Radcheck.objects.create(
                    username=username,
                    attribute="Max-Total-Octets",
                    op:=":=",
                    value=str(plan.data_limit * 1024 * 1024),  # Convert MB to bytes
                )

            vouchers.append(voucher)

        return vouchers

    @staticmethod
    def activate_voucher(voucher):
        """Called by FreeRADIUS post-auth to activate voucher."""
        if voucher.status == "unused":
            voucher.activate()
            return True
        return False

    @staticmethod
    @transaction.atomic
    def expire_vouchers():
        """Expire vouchers past their expiration time."""
        now = timezone.now()
        expired = Voucher.objects.filter(
            status="active",
            expires_at__lte=now,
        )
        count = expired.count()
        expired.update(status="expired")

        # Disable radcheck rows for expired vouchers
        for voucher in expired:
            Radcheck.objects.filter(username=voucher.username).delete()

        return count

    @staticmethod
    def disable_voucher(voucher):
        """Manually disable a voucher."""
        voucher.status = "disabled"
        voucher.save(update_fields=["status"])
        Radcheck.objects.filter(username=voucher.username).delete()
        return True


class PaystackService:
    """Paystack payment integration."""

    BASE_URL = "https://api.paystack.co"

    def __init__(self, secret_key):
        self.secret_key = secret_key
        self.headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        }

    def initialize_transaction(self, email, amount, reference=None, metadata=None):
        """Initialize a Paystack transaction."""
        data = {
            "email": email,
            "amount": amount,  # in kobo
            "metadata": metadata or {},
        }
        if reference:
            data["reference"] = reference

        response = requests.post(
            f"{self.BASE_URL}/transaction/initialize",
            json=data,
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def verify_transaction(self, reference):
        """Verify a Paystack transaction."""
        response = requests.get(
            f"{self.BASE_URL}/transaction/verify/{reference}",
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def create_customer(self, email, first_name="", last_name="", phone=""):
        """Create a Paystack customer."""
        data = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
        }
        response = requests.post(
            f"{self.BASE_URL}/customer",
            json=data,
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


class RadiusService:
    """FreeRADIUS session management."""

    @staticmethod
    def get_active_sessions(tenant=None):
        """Get active RADIUS sessions."""
        from .models import Radacct
        query = Radacct.objects.filter(acctstoptime__isnull=True)
        if tenant:
            # Filter by NAS IP belonging to tenant's routers
            from routers.models import NASDevice
            router_ips = NASDevice.objects.filter(tenant=tenant).values_list("ip_address", flat=True)
            query = query.filter(nasipaddress__in=router_ips)
        return query

    @staticmethod
    def disconnect_session(session_id, nas_ip, nas_port, callingsession_id, shared_secret):
        """Send CoA disconnect to RADIUS server."""
        # Implementation depends on RADIUS server configuration
        pass
```

### File: `vouchers/management/commands/expire_vouchers.py`
```python
from django.core.management.base import BaseCommand
from vouchers.services import VoucherService


class Command(BaseCommand):
    help = "Expire vouchers past their expiration time"

    def handle(self, *args, **options):
        count = VoucherService.expire_vouchers()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} vouchers."))
```

### File: `vouchers/management/commands/sync_vouchers.py`
```python
from django.core.management.base import BaseCommand
from vouchers.models import Voucher, Radcheck


class Command(BaseCommand):
    help = "Synchronize voucher state with RADIUS tables"

    def handle(self, *args, **options):
        # Ensure active vouchers have radcheck rows
        active = Voucher.objects.filter(status="active")
        created = 0
        for voucher in active:
            if not Radcheck.objects.filter(username=voucher.username).exists():
                Radcheck.objects.create(
                    username=voucher.username,
                    attribute="Cleartext-Password",
                    op=":=",
                    value=voucher.password,
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Synced {created} missing radcheck rows."))
```

### Commands to Run
```bash
python manage.py makemigrations vouchers
python manage.py migrate
python manage.py expire_vouchers   # Test the command
python manage.py sync_vouchers     # Test the command
```

---

## Prompt 6: Voucher API Endpoints

### What to Build
Full CRUD API for vouchers: list, detail, generate, disable, print, PDF.

### File: `vouchers/filters.py`
```python
import django_filters
from .models import Voucher, PaymentTransaction


class VoucherFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    plan = django_filters.NumberFilter(field_name="plan_id")
    search = django_filters.CharFilter(method="filter_search")
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Voucher
        fields = ["status", "plan", "search"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            models.Q(username__icontains=value) |
            models.Q(customer_name__icontains=value)
        )


class PaymentTransactionFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = PaymentTransaction
        fields = ["status", "search"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            models.Q(reference__icontains=value) |
            models.Q(customer_email__icontains=value) |
            models.Q(customer_name__icontains=value)
        )
```

### File: `vouchers/views.py`
```python
from rest_framework import viewsets, generics, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from .models import Voucher, InternetPlan, PaymentTransaction
from .serializers import (
    VoucherSerializer, InternetPlanSerializer,
    VoucherGenerateSerializer, PaymentTransactionSerializer,
)
from .services import VoucherService
from .filters import VoucherFilter, PaymentTransactionFilter
from core.permissions import IsTenantManager


class InternetPlanViewSet(viewsets.ModelViewSet):
    serializer_class = InternetPlanSerializer

    def get_queryset(self):
        return InternetPlan.objects.filter(tenant=self.request.user.membership.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.membership.tenant)


class VoucherViewSet(viewsets.ModelViewSet):
    serializer_class = VoucherSerializer
    filterset_class = VoucherFilter
    search_fields = ["username", "status"]
    ordering_fields = ["created_at", "status", "expires_at"]

    def get_queryset(self):
        return Voucher.objects.filter(tenant=self.request.user.membership.tenant)

    def get_permissions(self):
        if self.action in ["list", "retrieve", "print", "pdf"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        serializer = VoucherGenerateSerializer(data=request.data)
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
        html_string = render_to_string("vouchers/voucher_print.html", {"voucher": voucher})
        return HttpResponse(html_string, content_type="text/html")

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        voucher = self.get_object()
        html_string = render_to_string("vouchers/voucher_pdf.html", {"voucher": voucher})
        pdf = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="voucher_{voucher.username}.pdf"'
        return response


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentTransactionSerializer
    filterset_class = PaymentTransactionFilter

    def get_queryset(self):
        return PaymentTransaction.objects.filter(tenant=self.request.user.membership.tenant)
```

### File: `vouchers/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("plans", views.InternetPlanViewSet, basename="plan")
router.register("vouchers", views.VoucherViewSet, basename="voucher")
router.register("payments/transactions", views.PaymentTransactionViewSet, basename="payment-transaction")

urlpatterns = [
    path("", include(router.urls)),
]
```

### Commands to Run
```bash
python manage.py runserver
# Test: GET http://localhost:8000/api/v1/vouchers/
# Test: POST http://localhost:8000/api/v1/vouchers/generate/
```

---

## Prompt 7: Payment & Paystack Integration

### What to Build
Payment initialization, webhook handling, transaction verification.

### File: `payments/models.py`
```python
from django.db import models


class PaystackWebhookEvent(models.Model):
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments_webhookevent"
        ordering = ["-created_at"]
```

### File: `payments/services.py`
```python
from django.conf import settings
from vouchers.services import PaystackService


def get_paystack_service(tenant=None):
    """Get Paystack service with tenant-specific or global keys."""
    if tenant and hasattr(tenant, "settings"):
        return PaystackService(secret_key=tenant.settings.paystack_secret_key)
    return PaystackService(secret_key=settings.PAYSTACK_SECRET_KEY)
```

### File: `payments/webhooks.py`
```python
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.conf import settings
from .models import PaystackWebhookEvent
from .services import get_paystack_service
from vouchers.models import PaymentTransaction, Voucher
from vouchers.services import VoucherService
import json
import hashlib


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """Handle Paystack webhook events."""
    payload = json.loads(request.body)
    event_id = payload.get("data", {}).get("id")

    # Duplicate detection
    if PaystackWebhookEvent.objects.filter(event_id=str(event_id)).exists():
        return JsonResponse({"status": "duplicate"}, status=200)

    # Record event
    PaystackWebhookEvent.objects.create(
        event_id=str(event_id),
        event_type=payload.get("event", "unknown"),
        payload=payload,
    )

    # Verify signature
    signature = request.headers.get("x-paystack-signature")
    computed = hashlib.sha512(
        (settings.PAYSTACK_SECRET_KEY + request.body.decode()).encode()
    ).hexdigest()
    if signature != computed:
        return JsonResponse({"error": "Invalid signature"}, status=400)

    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        reference = data.get("reference")
        try:
            transaction = PaymentTransaction.objects.get(reference=reference)
            transaction.status = "success"
            transaction.paystack_reference = data.get("id")
            transaction.paid_at = data.get("paid_at")
            transaction.save()

            # Create voucher for successful payment
            if transaction.plan and not transaction.voucher:
                vouchers = VoucherService.generate_vouchers(
                    tenant=transaction.tenant,
                    plan_id=transaction.plan.id,
                    quantity=1,
                    source="customer",
                )
                transaction.voucher = vouchers[0]
                transaction.save()
        except PaymentTransaction.DoesNotExist:
            pass

    return JsonResponse({"status": "ok"})
```

### File: `payments/views.py`
```python
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .services import get_paystack_service
from .webhooks import paystack_webhook
from vouchers.models import PaymentTransaction, InternetPlan
import hashlib
import secrets


class InitializePaymentView(APIView):
    """Initialize a Paystack payment for voucher purchase."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        plan_id = request.data.get("plan_id")
        email = request.data.get("email")
        name = request.data.get("name", "")
        phone = request.data.get("phone", "")

        if not plan_id or not email:
            return Response(
                {"error": "plan_id and email are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan = InternetPlan.objects.get(id=plan_id, is_active=True)
        reference = f"yarotech-{secrets.token_hex(12)}"

        # Create pending transaction
        transaction = PaymentTransaction.objects.create(
            reference=reference,
            amount=plan.price,
            customer_email=email,
            customer_name=name,
            customer_phone=phone,
            plan=plan,
            tenant=plan.tenant,
        )

        # Initialize Paystack
        service = get_paystack_service(plan.tenant)
        result = service.initialize_transaction(
            email=email,
            amount=plan.price,
            reference=reference,
            metadata={
                "transaction_id": transaction.id,
                "plan_id": plan.id,
                "custom_fields": [
                    {"display_name": "Plan", "variable_name": "plan", "value": plan.name},
                ],
            },
        )

        return Response({
            "authorization_url": result["data"]["authorization_url"],
            "reference": reference,
        })


class PaymentCallbackView(APIView):
    """Handle Paystack return URL callback."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        reference = request.query_params.get("reference")
        if not reference:
            return Response({"error": "Missing reference"}, status=400)

        transaction = PaymentTransaction.objects.get(reference=reference)
        return Response({
            "status": transaction.status,
            "reference": reference,
            "voucher": transaction.voucher.username if transaction.voucher else None,
        })
```

### File: `payments/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

urlpatterns = [
    path("buy/", views.InitializePaymentView.as_view(), name="buy-voucher"),
    path("payments/callback/", views.PaymentCallbackView.as_view(), name="payment-callback"),
    path("payments/paystack/webhook/<str:token>/", views.paystack_webhook, name="paystack-webhook"),
]
```

### Commands to Run
```bash
python manage.py makemigrations payments
python manage.py migrate
```

---

## Prompt 8: Router Models & State Machine

### What to Build
NASDevice model with onboarding state machine, audit events, secret encryption.

### File: `routers/models.py`
```python
from django.db import models
from django.conf import settings
import uuid


class NASDevice(models.Model):
    ONBOARDING_STATES = [
        ("pending", "Pending"),
        ("reviewed", "Reviewed"),
        ("approved", "Approved"),
        ("waiting_for_vpn", "Waiting for VPN"),
        ("vpn_failed", "VPN Failed"),
        ("testing_radius", "Testing RADIUS"),
        ("radius_failed", "RADIUS Failed"),
        ("accounting_failed", "Accounting Failed"),
        ("active", "Active"),
        ("suspended", "Suspended"),
    ]

    DEPLOYMENT_STATUSES = [
        ("not_deployed", "Not Deployed"),
        ("deploying", "Deploying"),
        ("deployed", "Deployed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    nas_secret = models.CharField(max_length=255)
    wireguard_ip = models.GenericIPAddressField(blank=True, null=True)
    wireguard_public_key = models.CharField(max_length=255, blank=True)
    wireguard_port = models.PositiveIntegerField(default=51820)
    routeros_username = models.CharField(max_length=100, blank=True)
    routeros_password_encrypted = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=200, blank=True)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="routers")
    onboarding_state = models.CharField(max_length=30, choices=ONBOARDING_STATES, default="pending")
    deployment_status = models.CharField(max_length=20, choices=DEPLOYMENT_STATUSES, default="not_deployed")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "routers_nasdevice"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.ip_address})"


class RouterAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    router = models.ForeignKey(NASDevice, on_delete=models.CASCADE, related_name="audit_events")
    action = models.CharField(max_length=100)
    from_state = models.CharField(max_length=30, blank=True, null=True)
    to_state = models.CharField(max_length=30, blank=True, null=True)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routers_auditevent"
        ordering = ["-created_at"]


class RouterOnboardingCheck(models.Model):
    CHECK_TYPES = [
        ("ping", "Ping"),
        ("routeros_api", "RouterOS API"),
        ("wireguard_peer", "WireGuard Peer"),
        ("radius_auth", "RADIUS Auth"),
        ("radius_acct", "RADIUS Accounting"),
        ("firewall", "Firewall Rules"),
    ]

    router = models.ForeignKey(NASDevice, on_delete=models.CASCADE, related_name="onboarding_checks")
    check_type = models.CharField(max_length=30, choices=CHECK_TYPES)
    passed = models.BooleanField(default=False)
    details = models.JSONField(default=dict)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routers_onboardingcheck"
        unique_together = ["router", "check_type"]
```

### File: `routers/state_machine.py`
```python
from .models import NASDevice, RouterAuditEvent
import uuid


class RouterStateMachine:
    """Manage NASDevice onboarding state transitions."""

    VALID_TRANSITIONS = {
        "pending": ["reviewed"],
        "reviewed": ["approved", "pending"],
        "approved": ["waiting_for_vpn"],
        "waiting_for_vpn": ["vpn_failed", "testing_radius"],
        "vpn_failed": ["waiting_for_vpn", "suspended"],
        "testing_radius": ["radius_failed", "accounting_failed", "active"],
        "radius_failed": ["testing_radius", "suspended"],
        "accounting_failed": ["testing_radius", "suspended"],
        "active": ["suspended"],
        "suspended": ["active", "pending"],
    }

    @classmethod
    def can_transition(cls, from_state, to_state):
        return to_state in cls.VALID_TRANSITIONS.get(from_state, [])

    @classmethod
    def transition(cls, router, to_state, action="state_change", details=None):
        if not cls.can_transition(router.onboarding_state, to_state):
            raise ValueError(
                f"Invalid transition: {router.onboarding_state} -> {to_state}"
            )

        from_state = router.onboarding_state
        correlation_id = uuid.uuid4()

        router.onboarding_state = to_state
        router.save(update_fields=["onboarding_state", "updated_at"])

        RouterAuditEvent.objects.create(
            router=router,
            action=action,
            from_state=from_state,
            to_state=to_state,
            correlation_id=correlation_id,
            details=details or {},
        )

        return correlation_id
```

### File: `routers/secret_store.py`
```python
from cryptography.fernet import Fernet
from django.conf import settings


class SecretStore:
    """Fernet encryption for router credentials."""

    def __init__(self):
        self.cipher = Fernet(settings.FERNET_KEY.encode() if settings.FERNET_KEY else Fernet.generate_key())

    def encrypt(self, plaintext):
        if not plaintext:
            return ""
        if plaintext.startswith("enc:v1:"):
            return plaintext
        return "enc:v1:" + self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext):
        if not ciphertext:
            return ""
        if not ciphertext.startswith("enc:v1:"):
            return ciphertext
        return self.cipher.decrypt(ciphertext[7:].encode()).decode()


secret_store = SecretStore()
```

### File: `routers/serializers.py`
```python
from rest_framework import serializers
from .models import NASDevice, RouterAuditEvent, RouterOnboardingCheck


class NASDeviceSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = NASDevice
        fields = [
            "id", "name", "ip_address", "nas_secret", "wireguard_ip",
            "wireguard_public_key", "wireguard_port", "routeros_username",
            "routeros_password_encrypted", "location", "tenant", "tenant_name",
            "onboarding_state", "deployment_status", "is_active",
            "last_seen_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "onboarding_state", "deployment_status", "last_seen_at", "created_at", "updated_at"]
        extra_kwargs = {
            "nas_secret": {"write_only": True},
            "routeros_password_encrypted": {"write_only": True},
        }


class RouterAuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouterAuditEvent
        fields = [
            "id", "router", "action", "from_state", "to_state",
            "correlation_id", "details", "created_at",
        ]


class RouterOnboardingCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouterOnboardingCheck
        fields = ["id", "router", "check_type", "passed", "details", "checked_at"]
```

### File: `routers/views.py`
```python
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import NASDevice, RouterAuditEvent, RouterOnboardingCheck
from .serializers import (
    NASDeviceSerializer, RouterAuditEventSerializer,
    RouterOnboardingCheckSerializer,
)
from .state_machine import RouterStateMachine
from core.permissions import IsTenantManager


class NASDeviceViewSet(viewsets.ModelViewSet):
    serializer_class = NASDeviceSerializer

    def get_queryset(self):
        return NASDevice.objects.filter(tenant=self.request.user.membership.tenant)

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.membership.tenant)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        router = self.get_object()
        to_state = request.data.get("to_state")
        try:
            correlation_id = RouterStateMachine.transition(
                router, to_state, action="manual_transition"
            )
            return Response({"correlation_id": str(correlation_id)})
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def audit(self, request, pk=None):
        router = self.get_object()
        events = RouterAuditEvent.objects.filter(router=router)
        return Response(RouterAuditEventSerializer(events, many=True).data)

    @action(detail=True, methods=["get"])
    def checks(self, request, pk=None):
        router = self.get_object()
        checks = RouterOnboardingCheck.objects.filter(router=router)
        return Response(RouterOnboardingCheckSerializer(checks, many=True).data)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        router = self.get_object()
        # TODO: Implement RADIUS test through router
        return Response({"status": "testing", "message": "Test initiated."})
```

### File: `routers/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("routers", views.NASDeviceViewSet, basename="router")

urlpatterns = [
    path("", include(router.urls)),
]
```

### Commands to Run
```bash
python manage.py makemigrations routers
python manage.py migrate
```

---

## Prompt 9: Router Provisioning & WireGuard

### What to Build
Provisioning agent with HMAC authentication, WireGuard peer management, MikroTik automation.

### File: `routers/provisioners.py`
```python
import hmac
import hashlib
import time
import requests
from django.conf import settings


class ProvisioningAgentClient:
    """HMAC-authenticated client for provisioning agent."""

    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url

    def _sign(self, payload, timestamp):
        message = f"{timestamp}.{payload}"
        return hmac.new(
            self.api_key.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _request(self, method, endpoint, data=None):
        timestamp = str(int(time.time()))
        payload = json.dumps(data) if data else ""
        signature = self._sign(payload, timestamp)

        response = requests.request(
            method,
            f"{self.base_url}{endpoint}",
            json=data,
            headers={
                "X-Provisioning-Timestamp": timestamp,
                "X-Provisioning-Signature": signature,
                "X-Provisioning-Key-Id": self.api_key[:8],
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def provision_wireguard_peer(self, router_id, wireguard_ip, public_key):
        return self._request("POST", "/internal/router-provisioning/", {
            "action": "provision_wireguard_peer",
            "router_id": str(router_id),
            "wireguard_ip": wireguard_ip,
            "public_key": public_key,
        })

    def test_radius_authentication(self, router_id, username, password):
        return self._request("POST", "/internal/router-provisioning/", {
            "action": "test_radius_authentication",
            "router_id": str(router_id),
            "username": username,
            "password": password,
        })

    def suspend_wireguard_peer(self, router_id):
        return self._request("POST", "/internal/router-provisioning/", {
            "action": "suspend_wireguard_peer",
            "router_id": str(router_id),
        })


class WireGuardManager:
    """Manage WireGuard peers on VPS."""

    def __init__(self, vps_host, ssh_key):
        self.vps_host = vps_host
        self.ssh_key = ssh_key

    def create_peer(self, public_key, allowed_ip):
        """Add a WireGuard peer to the VPS."""
        # SSH into VPS and run wg set
        cmd = f"wg set wg0 peer {public_key} allowed-ips {allowed_ip}/32"
        # Execute via SSH
        return True

    def remove_peer(self, public_key):
        """Remove a WireGuard peer from the VPS."""
        cmd = f"wg set wg0 peer {public_key} remove"
        return True

    def list_peers(self):
        """List all WireGuard peers."""
        cmd = "wg show wg0 dump"
        # Parse output
        return []

    def get_peer_status(self, public_key):
        """Check if a peer is currently connected."""
        peers = self.list_peers()
        for peer in peers:
            if peer["public_key"] == public_key:
                return peer.get("latest_handshake", 0) > time.time() - 180
        return False
```

### File: `routers/provisioning_views.py`
```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.conf import settings
from django.core.cache import cache
from .models import NASDevice, ProvisioningAgentRequest
from .provisioners import WireGuardManager
from .secret_store import secret_store
import hmac
import hashlib
import time
import json


class ProvisioningAgentEndpoint(APIView):
    """HMAC-authenticated provisioning endpoint."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Authenticate via HMAC
        timestamp = request.headers.get("X-Provisioning-Timestamp", "")
        signature = request.headers.get("X-Provisioning-Signature", "")
        key_id = request.headers.get("X-Provisioning-Key-Id", "")

        # Verify timestamp freshness (5 minutes)
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 300:
                return Response({"error": "Request expired"}, status=401)
        except ValueError:
            return Response({"error": "Invalid timestamp"}, status=401)

        # Find matching API key
        agent_keys = settings.ROUTER_PROVISIONING_AGENT_KEYS
        matching_key = None
        for key in agent_keys:
            if key[:8] == key_id:
                matching_key = key
                break

        if not matching_key:
            return Response({"error": "Invalid key"}, status=401)

        # Verify signature
        payload = request.body.decode()
        message = f"{timestamp}.{payload}"
        computed = hmac.new(matching_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, computed):
            return Response({"error": "Invalid signature"}, status=401)

        # Deduplication
        request_id = request.data.get("request_id")
        if request_id and ProvisioningAgentRequest.objects.filter(request_id=request_id).exists():
            return Response({"error": "Duplicate request"}, status=409)

        # Rate limiting
        cache_key = f"provisioning_rate_{key_id}"
        count = cache.get(cache_key, 0)
        if count >= 120:
            return Response({"error": "Rate limit exceeded"}, status=429)
        cache.set(cache_key, count + 1, 60)

        # Process action
        action = request.data.get("action")
        router_id = request.data.get("router_id")

        try:
            router = NASDevice.objects.get(id=router_id)
        except NASDevice.DoesNotExist:
            return Response({"error": "Router not found"}, status=404)

        # Log request
        if request_id:
            ProvisioningAgentRequest.objects.create(
                request_id=request_id,
                key_id=key_id,
                action=action,
                router=router,
                payload=request.data,
            )

        # Dispatch action
        if action == "provision_wireguard_peer":
            wg_manager = WireGuardManager(settings.WG_VPS_HOST, settings.WG_VPS_SSH_KEY)
            wg_manager.create_peer(
                public_key=request.data["public_key"],
                allowed_ip=request.data["wireguard_ip"],
            )
            return Response({"status": "ok", "action": action})

        elif action == "suspend_wireguard_peer":
            wg_manager = WireGuardManager(settings.WG_VPS_HOST, settings.WG_VPS_SSH_KEY)
            wg_manager.remove_peer(public_key=router.wireguard_public_key)
            return Response({"status": "ok", "action": action})

        return Response({"error": "Unknown action"}, status=400)
```

### File: `routers/models.py` (add to existing)
```python
# Add to routers/models.py

class ProvisioningAgentRequest(models.Model):
    request_id = models.UUIDField(unique=True)
    key_id = models.CharField(max_length=16)
    action = models.CharField(max_length=50)
    router = models.ForeignKey(NASDevice, on_delete=models.CASCADE, null=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routers_provisioningrequest"
```

### File: `routers/urls.py` (update)
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .provisioning_views import ProvisioningAgentEndpoint

router = DefaultRouter()
router.register("routers", views.NASDeviceViewSet, basename="router")

urlpatterns = [
    path("", include(router.urls)),
    path("internal/router-provisioning/", ProvisioningAgentEndpoint.as_view(), name="provisioning-agent"),
]
```

### Commands to Run
```bash
python manage.py makemigrations routers
python manage.py migrate
```

---

## Prompt 10: Router API Endpoints

### What to Build
Full router CRUD, deployment status, health checks, session management.

### File: `routers/services.py`
```python
import subprocess
from django.utils import timezone
from .models import NASDevice


class RouterService:
    """Router management services."""

    @staticmethod
    def ping_router(ip_address):
        """Ping router to check reachability."""
        result = subprocess.run(
            ["ping", "-n", "3", ip_address],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0

    @staticmethod
    def refresh_router_status(router):
        """Check if router is online and update last_seen_at."""
        is_online = RouterService.ping_router(router.ip_address)
        if is_online:
            router.last_seen_at = timezone.now()
            router.save(update_fields=["last_seen_at"])
        return is_online

    @staticmethod
    def refresh_all_statuses(tenant=None):
        """Refresh status for all routers."""
        query = NASDevice.objects.filter(is_active=True)
        if tenant:
            query = query.filter(tenant=tenant)

        results = []
        for router in query:
            is_online = RouterService.refresh_router_status(router)
            results.append({
                "router_id": str(router.id),
                "name": router.name,
                "online": is_online,
            })
        return results

    @staticmethod
    def register_nas_client(router):
        """Register router in FreeRADIUS nas table."""
        from vouchers.models import Radcheck
        # Insert into nas table via raw SQL
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO nas (nasname, shortname, secret, type, ports, host_descriptor)
                VALUES (%s, %s, %s, 'other', 0, 'radius')
                ON CONFLICT (nasname) DO UPDATE SET secret = EXCLUDED.secret
                """,
                [router.ip_address, router.name, router.nas_secret],
            )
        return True
```

### File: `routers/management/commands/refresh_router_statuses.py`
```python
from django.core.management.base import BaseCommand
from routers.services import RouterService


class Command(BaseCommand):
    help = "Refresh router online/offline status"

    def handle(self, *args, **options):
        results = RouterService.refresh_all_statuses()
        online = sum(1 for r in results if r["online"])
        self.stdout.write(
            self.style.SUCCESS(f"Checked {len(results)} routers. {online} online.")
        )
```

### Commands to Run
```bash
python manage.py makemigrations routers
python manage.py migrate
python manage.py refresh_router_statuses  # Test
```

---

## Prompt 11: Agent Models & Wallet System

### What to Build
Agent profile, wallet, funding, voucher allocation, commission tracking.

### File: `agents/models.py`
```python
from django.db import models
from django.conf import settings


class AgentProfile(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("suspended", "Suspended"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_profile")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="agents")
    phone = models.CharField(max_length=20)
    shop_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_agentprofile"

    def __str__(self):
        return f"Agent: {self.user.username}"


class AgentWallet(models.Model):
    agent = models.OneToOneField(AgentProfile, on_delete=models.CASCADE, related_name="wallet")
    balance = models.PositiveIntegerField(default=0)  # in kobo
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agents_wallet"

    def __str__(self):
        return f"Wallet: {self.agent.user.username} (₦{self.balance / 100})"

    def credit(self, amount):
        self.balance += amount
        self.save(update_fields=["balance", "updated_at"])

    def debit(self, amount):
        if self.balance < amount:
            raise ValueError("Insufficient balance")
        self.balance -= amount
        self.save(update_fields=["balance", "updated_at"])


class AgentWalletFundingPayment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    wallet = models.ForeignKey(AgentWallet, on_delete=models.CASCADE, related_name="funding_payments")
    amount = models.PositiveIntegerField(help_text="Amount in kobo")
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    paystack_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agents_fundingpayment"
        ordering = ["-created_at"]


class AgentVoucherAllocation(models.Model):
    ALLOCATION_TYPES = [
        ("wallet", "Wallet"),
        ("credit", "Credit"),
        ("complimentary", "Complimentary"),
    ]

    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name="allocations")
    voucher = models.OneToOneField("vouchers.Voucher", on_delete=models.CASCADE, related_name="agent_allocation")
    allocation_type = models.CharField(max_length=20, choices=ALLOCATION_TYPES, default="wallet")
    amount_charged = models.PositiveIntegerField(default=0)  # in kobo
    commission_earned = models.PositiveIntegerField(default=0)  # in kobo
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_voucherallocation"
        ordering = ["-created_at"]


class AgentCreditAccount(models.Model):
    agent = models.OneToOneField(AgentProfile, on_delete=models.CASCADE, related_name="credit_account")
    credit_limit = models.PositiveIntegerField(default=0)  # in kobo
    current_balance = models.IntegerField(default=0)  # positive = owed to tenant, negative = credit remaining
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_creditaccount"


class AgentCreditLedger(models.Model):
    credit_account = models.ForeignKey(AgentCreditAccount, on_delete=models.CASCADE, related_name="ledger_entries")
    amount = models.IntegerField(help_text="Positive = charge, negative = payment")
    description = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_creditledger"
        ordering = ["-created_at"]
```

### File: `agents/services.py`
```python
from django.db import transaction
from .models import AgentProfile, AgentWallet, AgentVoucherAllocation, AgentCreditAccount
from vouchers.services import VoucherService


class AgentService:
    """Agent wallet and voucher operations."""

    @staticmethod
    @transaction.atomic
    def generate_voucher_from_wallet(agent, plan_id, quantity=1):
        """Generate vouchers funded from agent's wallet."""
        from vouchers.models import InternetPlan
        plan = InternetPlan.objects.get(id=plan_id, is_active=True, tenant=agent.tenant)
        wallet = agent.wallet
        total_cost = plan.price * quantity

        if wallet.balance < total_cost:
            raise ValueError("Insufficient wallet balance")

        # Debit wallet
        wallet.debit(total_cost)

        # Generate vouchers
        vouchers = VoucherService.generate_vouchers(
            tenant=agent.tenant,
            plan_id=plan_id,
            quantity=quantity,
            prefix=agent.tenant.settings.voucher_prefix if hasattr(agent.tenant, "settings") else "",
            agent=agent,
            source="agent",
        )

        # Create allocation records
        allocations = []
        for voucher in vouchers:
            allocation = AgentVoucherAllocation.objects.create(
                agent=agent,
                voucher=voucher,
                allocation_type="wallet",
                amount_charged=plan.price,
            )
            allocations.append(allocation)

        return vouchers, allocations

    @staticmethod
    @transaction.atomic
    def fund_wallet(agent, amount, reference):
        """Initialize wallet funding via Paystack."""
        from .models import AgentWalletFundingPayment
        wallet, _ = AgentWallet.objects.get_or_create(agent=agent)
        payment = AgentWalletFundingPayment.objects.create(
            wallet=wallet,
            amount=amount,
            reference=reference,
        )
        return payment

    @staticmethod
    @transaction.atomic
    def complete_wallet_funding(payment):
        """Credit wallet after successful payment."""
        payment.status = "success"
        payment.save(update_fields=["status"])
        payment.wallet.credit(payment.amount)

    @staticmethod
    def get_agent_stats(agent):
        """Get agent dashboard statistics."""
        wallet = agent.wallet
        from vouchers.models import Voucher
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.now().date()
        month_start = today.replace(day=1)

        vouchers_today = AgentVoucherAllocation.objects.filter(
            agent=agent, created_at__date=today
        ).count()

        commission_this_month = AgentVoucherAllocation.objects.filter(
            agent=agent, created_at__date__gte=month_start
        ).values_list("commission_earned", flat=True)

        return {
            "wallet_balance": wallet.balance,
            "vouchers_today": vouchers_today,
            "commission_this_month": sum(commission_this_month),
            "total_vouchers": AgentVoucherAllocation.objects.filter(agent=agent).count(),
        }
```

### File: `agents/serializers.py`
```python
from rest_framework import serializers
from .models import (
    AgentProfile, AgentWallet, AgentWalletFundingPayment,
    AgentVoucherAllocation, AgentCreditAccount,
)


class AgentProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    wallet_balance = serializers.IntegerField(source="wallet.balance", read_only=True, default=0)

    class Meta:
        model = AgentProfile
        fields = [
            "id", "user", "username", "tenant", "phone", "shop_name",
            "status", "commission_rate", "wallet_balance", "created_at",
        ]


class AgentWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentWallet
        fields = ["id", "agent", "balance", "updated_at"]


class AgentWalletFundingSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=500, help_text="Minimum ₦500")


class AgentVoucherAllocationSerializer(serializers.ModelSerializer):
    voucher_username = serializers.CharField(source="voucher.username", read_only=True)

    class Meta:
        model = AgentVoucherAllocation
        fields = [
            "id", "agent", "voucher", "voucher_username",
            "allocation_type", "amount_charged", "commission_earned", "created_at",
        ]


class AgentStatsSerializer(serializers.Serializer):
    wallet_balance = serializers.IntegerField()
    vouchers_today = serializers.IntegerField()
    commission_this_month = serializers.IntegerField()
    total_vouchers = serializers.IntegerField()
```

### File: `agents/views.py`
```python
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import AgentProfile, AgentWallet, AgentVoucherAllocation
from .serializers import (
    AgentProfileSerializer, AgentWalletSerializer,
    AgentVoucherAllocationSerializer, AgentStatsSerializer,
    AgentWalletFundingSerializer,
)
from .services import AgentService
from core.permissions import IsAgent


class AgentProfileViewSet(viewsets.ModelViewSet):
    serializer_class = AgentProfileSerializer
    permission_classes = [IsAgent]

    def get_queryset(self):
        return AgentProfile.objects.filter(user=self.request.user)

    @action(detail=False, methods=["get"])
    def me(self, request):
        profile = AgentProfile.objects.get(user=request.user)
        return Response(AgentProfileSerializer(profile).data)


class AgentWalletViewSet(viewsets.GenericViewSet):
    serializer_class = AgentWalletSerializer
    permission_classes = [IsAgent]

    @action(detail=False, methods=["get"])
    def balance(self, request):
        wallet, _ = AgentWallet.objects.get_or_create(
            agent=request.user.agent_profile
        )
        return Response(AgentWalletSerializer(wallet).data)

    @action(detail=False, methods=["post"])
    def fund(self, request):
        serializer = AgentWalletFundingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        import secrets
        reference = f"agent-fund-{secrets.token_hex(12)}"
        payment = AgentService.fund_wallet(
            agent=request.user.agent_profile,
            amount=serializer.validated_data["amount"],
            reference=reference,
        )

        # Initialize Paystack
        from payments.services import get_paystack_service
        service = get_paystack_service(request.user.agent_profile.tenant)
        result = service.initialize_transaction(
            email=request.user.email,
            amount=payment.amount,
            reference=reference,
        )

        return Response({
            "authorization_url": result["data"]["authorization_url"],
            "reference": reference,
        })


class AgentVoucherGenerateView(viewsets.GenericViewSet):
    permission_classes = [IsAgent]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        plan_id = request.data.get("plan_id")
        quantity = request.data.get("quantity", 1)

        try:
            vouchers, allocations = AgentService.generate_voucher_from_wallet(
                agent=request.user.agent_profile,
                plan_id=plan_id,
                quantity=quantity,
            )
            return Response({
                "vouchers": AgentVoucherAllocationSerializer(allocations, many=True).data,
            }, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def history(self, request):
        allocations = AgentVoucherAllocation.objects.filter(
            agent=request.user.agent_profile
        )
        return Response(AgentVoucherAllocationSerializer(allocations, many=True).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        stats = AgentService.get_agent_stats(request.user.agent_profile)
        return Response(AgentStatsSerializer(stats).data)
```

### File: `agents/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("agents", views.AgentProfileViewSet, basename="agent")
router.register("agent/wallet", views.AgentWalletViewSet, basename="agent-wallet")
router.register("agent/vouchers", views.AgentVoucherGenerateView, basename="agent-voucher")

urlpatterns = [
    path("", include(router.urls)),
]
```

### Commands to Run
```bash
python manage.py makemigrations agents
python manage.py migrate
```

---

## Prompt 12: Agent API Endpoints

### What to Build
Agent-specific authentication, dashboard, voucher generation, wallet operations.

### File: `agents/auth_views.py`
```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .models import AgentProfile

User = get_user_model()


class AgentLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = User.objects.filter(username=username).first()
        if user and user.check_password(password):
            if not hasattr(user, "agent_profile"):
                return Response(
                    {"error": "Not an agent account"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if user.agent_profile.status != "active":
                return Response(
                    {"error": "Agent account is not active"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "agent": {
                    "id": user.agent_profile.id,
                    "username": user.username,
                    "shop_name": user.agent_profile.shop_name,
                },
            })

        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )


class AgentDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .services import AgentService
        stats = AgentService.get_agent_stats(request.user.agent_profile)
        return Response(stats)
```

### File: `agents/urls.py` (update)
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .auth_views import AgentLoginView, AgentDashboardView

router = DefaultRouter()
router.register("agents", views.AgentProfileViewSet, basename="agent")
router.register("agent/wallet", views.AgentWalletViewSet, basename="agent-wallet")
router.register("agent/vouchers", views.AgentVoucherGenerateView, basename="agent-voucher")

urlpatterns = [
    path("", include(router.urls)),
    path("agent/login/", AgentLoginView.as_view(), name="agent-login"),
    path("agent/dashboard/", AgentDashboardView.as_view(), name="agent-dashboard"),
]
```

### Commands to Run
```bash
python manage.py runserver
# Test: POST http://localhost:8000/api/v1/agent/login/
```

---

## Prompt 13: Subscription & Billing

### What to Build
Subscription plans, tenant subscriptions, trial management, billing.

### File: `subscriptions/models.py`
```python
from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.PositiveIntegerField(help_text="Price in kobo")
    duration_days = models.PositiveIntegerField()
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_plan"
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} - ₦{self.price / 100}"


class TenantSubscription(models.Model):
    STATUS_CHOICES = [
        ("trial", "Trial"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ]

    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="trial")
    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    is_trial = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_tenantsubscription"

    def __str__(self):
        return f"{self.tenant.name} - {self.plan.name} ({self.status})"

    @property
    def is_active(self):
        return self.status in ("trial", "active") and self.expires_at > timezone.now()


class SubscriptionPayment(models.Model):
    subscription = models.ForeignKey(TenantSubscription, on_delete=models.CASCADE, related_name="payments")
    reference = models.CharField(max_length=100, unique=True)
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "subscriptions_payment"
```

### File: `subscriptions/serializers.py`
```python
from rest_framework import serializers
from .models import SubscriptionPlan, TenantSubscription, SubscriptionPayment


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    price_display = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "price", "price_display", "duration_days", "features", "is_active"]

    def get_price_display(self, obj):
        return f"₦{obj.price / 100:,.0f}"


class TenantSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = TenantSubscription
        fields = [
            "id", "tenant", "plan", "plan_name", "status",
            "started_at", "expires_at", "is_trial", "is_expired",
        ]

    def get_is_expired(self, obj):
        return not obj.is_active
```

### File: `subscriptions/views.py`
```python
from rest_framework import viewsets, generics, status, permissions
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from .models import SubscriptionPlan, TenantSubscription
from .serializers import SubscriptionPlanSerializer, TenantSubscriptionSerializer


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    permission_classes = [permissions.AllowAny]


class TenantSubscriptionView(generics.RetrieveUpdateAPIView):
    serializer_class = TenantSubscriptionSerializer

    def get_object(self):
        sub, _ = TenantSubscription.objects.get_or_create(
            tenant=self.request.user.membership.tenant,
            defaults={
                "plan": SubscriptionPlan.objects.first(),
                "status": "trial",
                "expires_at": timezone.now() + timedelta(days=30),
                "is_trial": True,
            },
        )
        return sub
```

### File: `subscriptions/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("pricing", views.SubscriptionPlanViewSet, basename="subscription-plan")

urlpatterns = [
    path("", include(router.urls)),
    path("subscriptions/", views.TenantSubscriptionView.as_view(), name="tenant-subscription"),
]
```

### Commands to Run
```bash
python manage.py makemigrations subscriptions
python manage.py migrate
```

---

## Prompt 14: WhatsApp Integration

### What to Build
WhatsApp route tokens, webhook handling, message processing, voucher reminders.

### File: `whatsapp_routing/models.py`
```python
from django.db import models
import hmac
import hashlib
import secrets


class TenantWhatsAppRoute(models.Model):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="whatsapp_route")
    phone_number_id = models.CharField(max_length=100)
    access_token_encrypted = models.CharField(max_length=500)
    webhook_token = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "whatsapp_tenantwhatsapproute"

    def __str__(self):
        return f"WhatsApp Route: {self.tenant.name}"

    def generate_route_token(self):
        """Generate HMAC-signed route token."""
        selector = secrets.token_hex(8)
        signature = hmac.new(
            self.webhook_token.encode(),
            selector.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        return f"{selector}.{signature}"

    @staticmethod
    def resolve_route_token(token):
        """Resolve a route token to its tenant."""
        try:
            selector, signature = token.split(".")
            routes = TenantWhatsAppRoute.objects.filter(is_active=True)
            for route in routes:
                expected = hmac.new(
                    route.webhook_token.encode(),
                    selector.encode(),
                    hashlib.sha256,
                ).hexdigest()[:16]
                if hmac.compare_digest(signature, expected):
                    return route.tenant
        except (ValueError, AttributeError):
            pass
        return None


class WhatsAppSenderBinding(models.Model):
    phone_number = models.CharField(max_length=20)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="whatsapp_bindings")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "whatsapp_senderbinding"
        unique_together = ["phone_number"]
```

### File: `whatsapp_routing/services.py`
```python
from .models import TenantWhatsAppRoute
import hmac
import hashlib


def generate_route_url(tenant, base_url="https://wa.me"):
    """Generate wa.me link with route token."""
    try:
        route = TenantWhatsAppRoute.objects.get(tenant=tenant, is_active=True)
        token = route.generate_route_token()
        return f"{base_url}/1234567890?text={token}"
    except TenantWhatsAppRoute.DoesNotExist:
        return None


def resolve_route_token(token):
    """Resolve incoming WhatsApp route token to tenant."""
    return TenantWhatsAppRoute.resolve_route_token(token)
```

### File: `whatsapp_routing/views.py`
```python
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from .models import TenantWhatsAppRoute
from .serializers import TenantWhatsAppRouteSerializer


class WhatsAppRouteViewSet(viewsets.ModelViewSet):
    serializer_class = TenantWhatsAppRouteSerializer

    def get_queryset(self):
        return TenantWhatsAppRoute.objects.filter(tenant=self.request.user.membership.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.membership.tenant)
```

### File: `whatsapp_routing/serializers.py`
```python
from rest_framework import serializers
from .models import TenantWhatsAppRoute


class TenantWhatsAppRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantWhatsAppRoute
        fields = ["id", "tenant", "phone_number_id", "webhook_token", "is_active", "created_at"]
        extra_kwargs = {
            "access_token_encrypted": {"write_only": True},
            "webhook_token": {"read_only": True},
        }
```

### File: `whatsapp_routing/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("whatsapp/routes", views.WhatsAppRouteViewSet, basename="whatsapp-route")

urlpatterns = [
    path("", include(router.urls)),
]
```

### Commands to Run
```bash
python manage.py makemigrations whatsapp_routing
python manage.py migrate
```

---

## Prompt 15: MAC Devices, Admin & Management Commands

### What to Build
IoT/MAC device management, Django admin configuration, all management commands.

### File: `iot_devices/models.py`
```python
from django.db import models


class MacDevice(models.Model):
    mac_address = models.CharField(max_length=17, unique=True)
    device_name = models.CharField(max_length=200)
    plan = models.ForeignKey("vouchers.InternetPlan", on_delete=models.PROTECT, related_name="mac_devices")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="mac_devices")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iot_macdevice"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.device_name} ({self.mac_address})"

    @staticmethod
    def normalize_mac(mac):
        """Normalize MAC address to XX:XX:XX:XX:XX:XX format."""
        mac = mac.replace("-", ":").replace(".", ":").upper()
        if len(mac) == 12:
            mac = ":".join(mac[i:i+2] for i in range(0, 12, 2))
        return mac
```

### File: `iot_devices/serializers.py`
```python
from rest_framework import serializers
from .models import MacDevice


class MacDeviceSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = MacDevice
        fields = [
            "id", "mac_address", "device_name", "plan", "plan_name",
            "tenant", "is_active", "expires_at", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_mac_address(self, value):
        return MacDevice.normalize_mac(value)
```

### File: `iot_devices/views.py`
```python
from rest_framework import viewsets
from .models import MacDevice
from .serializers import MacDeviceSerializer


class MacDeviceViewSet(viewsets.ModelViewSet):
    serializer_class = MacDeviceSerializer

    def get_queryset(self):
        return MacDevice.objects.filter(tenant=self.request.user.membership.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.membership.tenant)
```

### File: `iot_devices/urls.py`
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("iot-devices", views.MacDeviceViewSet, basename="iot-device")

urlpatterns = [
    path("", include(router.urls)),
]
```

### File: `dashboard/views.py`
```python
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta


class DashboardStatsView(APIView):
    def get(self, request):
        tenant = request.user.membership.tenant
        from vouchers.models import Voucher, PaymentTransaction
        from routers.models import NASDevice
        from agents.models import AgentProfile

        today = timezone.now().date()
        month_start = today.replace(day=1)

        return Response({
            "total_vouchers": Voucher.objects.filter(tenant=tenant).count(),
            "active_vouchers": Voucher.objects.filter(tenant=tenant, status="active").count(),
            "total_revenue": PaymentTransaction.objects.filter(
                tenant=tenant, status="success"
            ).aggregate(total=Sum("amount"))["total"] or 0,
            "total_agents": AgentProfile.objects.filter(tenant=tenant).count(),
            "total_routers": NASDevice.objects.filter(tenant=tenant).count(),
            "active_routers": NASDevice.objects.filter(
                tenant=tenant, onboarding_state="active"
            ).count(),
        })


class LiveUsersView(APIView):
    def get(self, request):
        from vouchers.models import Radacct
        from routers.models import NASDevice

        tenant = request.user.membership.tenant
        router_ips = NASDevice.objects.filter(tenant=tenant).values_list("ip_address", flat=True)
        sessions = Radacct.objects.filter(
            nasipaddress__in=router_ips,
            acctstoptime__isnull=True,
        )

        users = []
        for session in sessions:
            users.append({
                "username": session.username,
                "ip_address": session.nasipaddress,
                "session_time": session.acctsessiontime,
                "bytes_in": session.acctinputoctets,
                "bytes_out": session.acctoutputoctets,
                "connected_at": session.acctstarttime,
            })

        return Response({"users": users, "count": len(users)})
```

### File: `dashboard/urls.py`
```python
from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/stats/", views.DashboardStatsView.as_view(), name="dashboard-stats"),
    path("dashboard/live-users/", views.LiveUsersView.as_view(), name="live-users"),
]
```

### File: `vouchers/admin.py`
```python
from django.contrib import admin
from .models import (
    InternetPlan, Voucher, PaymentTransaction,
    Radcheck, Radreply, Radacct, Radpostauth,
)


@admin.register(InternetPlan)
class InternetPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "price", "duration_hours", "rate_limit", "is_active"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["name"]


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ["username", "plan", "status", "tenant", "created_at"]
    list_filter = ["status", "plan", "tenant"]
    search_fields = ["username"]
    readonly_fields = ["username", "password"]


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ["reference", "amount", "status", "customer_email", "created_at"]
    list_filter = ["status"]
    search_fields = ["reference", "customer_email"]


@admin.register(Radcheck)
class RadcheckAdmin(admin.ModelAdmin):
    list_display = ["username", "attribute", "op", "value"]
    search_fields = ["username"]


@admin.register(Radacct)
class RadacctAdmin(admin.ModelAdmin):
    list_display = ["username", "nasipaddress", "acctstarttime", "acctstoptime"]
    search_fields = ["username"]
```

### Commands to Run
```bash
python manage.py makemigrations iot_devices dashboard
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# Visit http://localhost:8000/admin/
```

---

## Final Integration Checklist

After completing all 15 prompts, verify everything works:

```bash
# 1. Run all migrations
python manage.py makemigrations
python manage.py migrate

# 2. Create superuser
python manage.py createsuperuser

# 3. Run development server
python manage.py runserver

# 4. Verify API docs
# Visit http://localhost:8000/api/docs/

# 5. Run tests
python manage.py test

# 6. Run management commands
python manage.py expire_vouchers
python manage.py sync_vouchers
python manage.py refresh_router_statuses
```

### Complete API Endpoint Map

| Method | Endpoint | View | Auth |
|--------|----------|------|------|
| POST | `/api/v1/auth/login/` | LoginView | AllowAny |
| POST | `/api/v1/auth/register/` | RegisterView | AllowAny |
| GET | `/api/v1/auth/user/` | CurrentUserView | IsAuthenticated |
| POST | `/api/v1/auth/change-password/` | ChangePasswordView | IsAuthenticated |
| POST | `/api/v1/auth/token/refresh/` | TokenRefreshView | AllowAny |
| GET/PUT | `/api/v1/tenants/settings/` | TenantSettingView | IsAuthenticated |
| GET/POST | `/api/v1/tenants/` | TenantViewSet | IsAuthenticated |
| GET/POST | `/api/v1/plans/` | InternetPlanViewSet | IsAuthenticated |
| GET/POST | `/api/v1/vouchers/` | VoucherViewSet | IsAuthenticated |
| POST | `/api/v1/vouchers/generate/` | VoucherViewSet.generate | IsTenantManager |
| POST | `/api/v1/vouchers/:id/disable/` | VoucherViewSet.disable | IsTenantManager |
| GET | `/api/v1/vouchers/:id/print/` | VoucherViewSet.print | IsAuthenticated |
| GET | `/api/v1/vouchers/:id/pdf/` | VoucherViewSet.pdf | IsAuthenticated |
| GET/POST | `/api/v1/routers/` | NASDeviceViewSet | IsAuthenticated |
| POST | `/api/v1/routers/create/` | NASDeviceViewSet | IsTenantManager |
| POST | `/api/v1/routers/:id/transition/` | NASDeviceViewSet.transition | IsTenantManager |
| GET | `/api/v1/routers/:id/audit/` | NASDeviceViewSet.audit | IsAuthenticated |
| GET | `/api/v1/routers/:id/checks/` | NASDeviceViewSet.checks | IsAuthenticated |
| POST | `/api/v1/routers/:id/test/` | NASDeviceViewSet.test | IsTenantManager |
| POST | `/api/v1/internal/router-provisioning/` | ProvisioningAgentEndpoint | HMAC |
| POST | `/api/v1/agent/login/` | AgentLoginView | AllowAny |
| GET | `/api/v1/agent/dashboard/` | AgentDashboardView | IsAuthenticated |
| GET | `/api/v1/agent/wallet/balance/` | AgentWalletViewSet.balance | IsAgent |
| POST | `/api/v1/agent/wallet/fund/` | AgentWalletViewSet.fund | IsAgent |
| POST | `/api/v1/agent/vouchers/generate/` | AgentVoucherGenerateView.generate | IsAgent |
| GET | `/api/v1/agent/vouchers/history/` | AgentVoucherGenerateView.history | IsAgent |
| GET | `/api/v1/agent/vouchers/stats/` | AgentVoucherGenerateView.stats | IsAgent |
| POST | `/api/v1/buy/` | InitializePaymentView | AllowAny |
| GET | `/api/v1/payments/callback/` | PaymentCallbackView | AllowAny |
| POST | `/api/v1/payments/paystack/webhook/:token/` | paystack_webhook | AllowAny |
| GET | `/api/v1/pricing/` | SubscriptionPlanViewSet | AllowAny |
| GET/PUT | `/api/v1/subscriptions/` | TenantSubscriptionView | IsAuthenticated |
| GET/POST | `/api/v1/whatsapp/routes/` | WhatsAppRouteViewSet | IsAuthenticated |
| GET/POST | `/api/v1/iot-devices/` | MacDeviceViewSet | IsAuthenticated |
| GET | `/api/v1/dashboard/stats/` | DashboardStatsView | IsAuthenticated |
| GET | `/api/v1/dashboard/live-users/` | LiveUsersView | IsAuthenticated |

### Full Requirements (`requirements.txt`)
```
django==5.1
djangorestframework==3.15.2
djangorestframework-simplejwt==5.3.1
psycopg2-binary==2.9.9
python-decouple==3.8
django-cors-headers==4.4.0
django-filter==24.3
drf-spectacular==0.27.2
requests==2.32.3
qrcode==7.4.2
Pillow==10.4.0
cryptography==43.0.0
pyotp==2.9.0
weasyprint==62.3
fpdf2==2.7.9
pytest==8.3.3
pytest-django==4.8.0
```
