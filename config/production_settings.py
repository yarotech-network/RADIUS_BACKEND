from django.core.exceptions import ImproperlyConfigured
from cryptography.fernet import Fernet

from .settings import *  # noqa: F403
from .settings import config


DEBUG = False

SECRET_KEY = config("SECRET_KEY", default="")
if len(SECRET_KEY) < 50 or SECRET_KEY == "change-me-in-production":
    raise ImproperlyConfigured(
        "Production SECRET_KEY must be set to a unique value of at least 50 characters."
    )

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="", cast=Csv())  # noqa: F405
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Production ALLOWED_HOSTS must contain explicit hostnames and must not use '*'."
    )

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
if not CORS_ALLOWED_ORIGINS or any(
    not origin.startswith("https://") for origin in CORS_ALLOWED_ORIGINS
):
    raise ImproperlyConfigured(
        "Production CORS_ALLOWED_ORIGINS must contain explicit HTTPS origins."
    )
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default=",".join(CORS_ALLOWED_ORIGINS),
    cast=Csv(),
)

REDIS_URL = config("REDIS_URL", default="")
if not REDIS_URL.startswith(("redis://", "rediss://")):
    raise ImproperlyConfigured("Production REDIS_URL must be configured.")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
        },
        "KEY_PREFIX": "yarotech-radius",
    }
}

PASSWORD_RESET_FRONTEND_URL = config("PASSWORD_RESET_FRONTEND_URL", default="")
if not PASSWORD_RESET_FRONTEND_URL.startswith("https://"):
    raise ImproperlyConfigured(
        "Production PASSWORD_RESET_FRONTEND_URL must use HTTPS."
    )

FERNET_KEY = config("FERNET_KEY", default="")
try:
    Fernet(FERNET_KEY.encode())
except (TypeError, ValueError) as exc:
    raise ImproperlyConfigured(
        "Production FERNET_KEY must be a stable valid Fernet key."
    ) from exc
if "{uid}" not in PASSWORD_RESET_FRONTEND_URL or "{token}" not in PASSWORD_RESET_FRONTEND_URL:
    raise ImproperlyConfigured(
        "PASSWORD_RESET_FRONTEND_URL must contain both {uid} and {token} placeholders."
    )

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=3600, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool
)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Enable this only when the application is behind a trusted proxy that removes
# client-supplied X-Forwarded-Proto and sets its own value.
if config("TRUST_X_FORWARDED_PROTO", default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CONN_MAX_AGE = config("DB_CONN_MAX_AGE", default=60, cast=int)
DATABASES["default"]["CONN_MAX_AGE"] = CONN_MAX_AGE  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
