"""
Verification-only Django settings: SQLite instead of PostgreSQL so the frontend can be exercised
against the real API code in a sandbox without Postgres. NOT for deployment.
"""
import os

os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("SECRET_KEY", "harness-secret-key-that-is-definitely-longer-than-32-bytes")
os.environ.setdefault("FERNET_KEY", "HnO9huZ1IHrosHOCcMgJaD5loIi43v3F1bUZxSIpTgk=")
os.environ.setdefault("ALLOWED_HOSTS", "*")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

from config.settings import *  # noqa: F401,F403,E402

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(os.path.dirname(__file__), "harness.sqlite3"),
    }
}
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Throttles stay ON so the UI's 429 handling can be checked.
