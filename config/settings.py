import os
import sys
from pathlib import Path
from decouple import config, Csv
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.join(BASE_DIR, "apps"))

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
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # Local apps
    "apps.core",
    "apps.accounts",
    "apps.tenants",
    "apps.vouchers",
    "apps.customers",
    "apps.routers",
    "apps.agents",
    "apps.payments",
    "apps.subscriptions",
    "apps.whatsapp_routing",
    "apps.iot_devices",
    "apps.dashboard",
]

MIDDLEWARE = [
    "apps.core.middleware.ApiErrorEnvelopeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.tenants.middleware.TenantMiddleware",
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
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
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
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/minute",
        "password_reset": "5/hour",
        "email_verify": "10/minute",
        "email_resend": "3/minute",
        "router_radius_test": "10/minute",
        "router_hotspot_setup": "30/minute",
        "router_discovery": "3/minute",
        "subscription_verify": "10/minute",
        "storefront_verify": "10/minute",
    },
}

# === SimpleJWT ===
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "CHECK_REVOKE_TOKEN": True,
}

# === CORS ===
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = [*default_headers, "idempotency-key", "x-tenant-id"]
CORS_EXPOSE_HEADERS = ["Idempotency-Replayed", "Retry-After"]

# === DRF Spectacular ===
SPECTACULAR_SETTINGS = {
    "POSTPROCESSING_HOOKS": ["drf_spectacular.hooks.postprocess_schema_enums", "apps.core.schema.annotate_api_errors_and_commands"],
    "ENUM_NAME_OVERRIDES": {
        "HotspotServiceEnum": [("hotspot", "hotspot")],
        "OnboardingStateEnum": "apps.routers.models.NASDevice.ONBOARDING_STATES",
        "AgentStatusEnum": "apps.agents.models.AgentProfile.STATUS_CHOICES",
        "VoucherStatusEnum": "apps.vouchers.models.Voucher.STATUS_CHOICES",
        "PaymentStatusEnum": "apps.vouchers.models.PaymentTransaction.STATUS_CHOICES",
        "FundingStatusEnum": "apps.agents.models.AgentWalletFundingPayment.STATUS_CHOICES",
        "SubscriptionStatusEnum": "apps.subscriptions.models.TenantSubscription.STATUS_CHOICES",
    },
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
WG_SSH_KNOWN_HOSTS = config("WG_SSH_KNOWN_HOSTS", default="")
WG_INTERFACE = config("WG_INTERFACE", default="wg0")
WG_MANAGED_SUBNET = config("WG_MANAGED_SUBNET", default="10.100.100.0/24")
WG_SSH_USE_SUDO = config("WG_SSH_USE_SUDO", default=True, cast=bool)
WG_SAVE_CONFIG = config("WG_SAVE_CONFIG", default=True, cast=bool)

# === RADIUS authentication probe ===
RADIUS_AUTH_HOST = config("RADIUS_AUTH_HOST", default="127.0.0.1")
RADIUS_AUTH_PORT = config("RADIUS_AUTH_PORT", default=1812, cast=int)
RADIUS_AUTH_TIMEOUT = config("RADIUS_AUTH_TIMEOUT", default=3.0, cast=float)
RADIUS_COA_PORT = config("RADIUS_COA_PORT", default=3799, cast=int)
RADIUS_COA_TIMEOUT = config("RADIUS_COA_TIMEOUT", default=3.0, cast=float)

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
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="no-reply@yarotech.local")
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=30, cast=int)
# Voucher access-code emails go through Resend (https://resend.com) when a key is configured;
# DEFAULT_FROM_EMAIL must then belong to a domain verified in Resend. Without a key the delivery
# worker falls back to EMAIL_BACKEND (console in development).
RESEND_API_KEY = config("RESEND_API_KEY", default="")
PASSWORD_RESET_FRONTEND_URL = config(
    "PASSWORD_RESET_FRONTEND_URL",
    default="http://localhost:5173/reset-password?uid={uid}&token={token}",
)
PASSWORD_RESET_TIMEOUT = config("PASSWORD_RESET_TIMEOUT", default=3600, cast=int)

# Browser return origin; never derive this from an untrusted request Host or payload.
from apps.payments.callbacks import validate_callback_origin
PAYSTACK_CALLBACK_ORIGIN = validate_callback_origin(config(
    "PAYSTACK_CALLBACK_ORIGIN", default="http://localhost:5173",
))

# Optional registration-only delivery override (e.g. console for local OTP testing).
REGISTRATION_EMAIL_BACKEND = config("REGISTRATION_EMAIL_BACKEND", default="")


# Read-only RouterOS discovery. Approve management peers explicitly; never public URLs.
ROUTER_DISCOVERY_ALLOWED_CIDRS = config("ROUTER_DISCOVERY_ALLOWED_CIDRS", default="", cast=Csv())
ROUTER_DISCOVERY_HTTPS_PORT = config("ROUTER_DISCOVERY_HTTPS_PORT", default=443, cast=int)
ROUTER_DISCOVERY_CA_BUNDLE = config("ROUTER_DISCOVERY_CA_BUNDLE", default="")

# Private FreeRADIUS PAP integration; unset disables the decision endpoint.
PPPOE_RADIUS_TOKEN = config("PPPOE_RADIUS_TOKEN", default="")
