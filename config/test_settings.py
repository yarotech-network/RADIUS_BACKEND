import os


# Test execution must not inherit an invalid or production-oriented DEBUG value.
os.environ["DEBUG"] = "False"

from .settings import *  # noqa: F403, E402


SECRET_KEY = "test-only-secret-key-that-is-at-least-32-bytes-long"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
FERNET_KEY = "HnO9huZ1IHrosHOCcMgJaD5loIi43v3F1bUZxSIpTgk="

# Django creates and destroys this PostgreSQL database independently of the
# configured development database.
DATABASES["default"]["TEST"] = {  # noqa: F405
    "NAME": os.environ.get("DB_TEST_NAME", "test_yarotech_radius"),
}
DATABASES["default"]["HOST"] = os.environ.get("DB_TEST_HOST", "localhost")  # noqa: F405
DATABASES["default"]["PORT"] = os.environ.get("DB_TEST_PORT", "5432")  # noqa: F405
