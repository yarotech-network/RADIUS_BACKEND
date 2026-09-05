"""Opt-in real-browser contract test using Django's isolated test database."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from unittest import skipUnless
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import LiveServerTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient


@skipUnless(os.environ.get("RUN_AUTH_BROWSER_TESTS") == "1", "Opt-in browser test; set RUN_AUTH_BROWSER_TESTS=1")
@override_settings(
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CORS_ALLOWED_ORIGINS=["http://127.0.0.1:4189"],
    PASSWORD_RESET_FRONTEND_URL="http://127.0.0.1:4189/reset-password?uid={uid}&token={token}",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "password-reset-browser"}},
)
class PasswordResetBrowserTests(LiveServerTestCase):
    def test_reset_browser_journeys_and_saved_passwords(self):
        frontend = Path(__file__).resolve().parents[3] / "frontend"
        node = shutil.which("node")
        cli = frontend / "node_modules" / "@playwright" / "test" / "cli.js"
        self.assertIsNotNone(node, "Node.js must be available for the browser test.")
        self.assertTrue(cli.is_file(), "Install the frontend dependencies before running this test.")
        users = {}
        fixtures = {}
        old_password = "Browser-Original-Password-7392"
        User = get_user_model()
        for project in ("chromium", "mobile-chrome"):
            for link_format in ("query", "path"):
                key = f"{project}-{link_format}"
                user = User.objects.create_user(
                    username=f"reset-browser-{key}",
                    email=f"reset-browser-{key}@example.invalid",
                    password=old_password,
                )
                users[key] = user.pk
                # Keep the successful-reset password unrelated to the username
                # and email. Fail setup immediately if Django rejects it.
                replacement_password = "Cobalt!7392-Meadow#6481"
                validate_password(replacement_password, user=user)
                client = APIClient()
                # Separate source address from browser requests so the setup
                # doesn't consume the browser's rate limit.
                result = client.post(
                    reverse("password-reset"), {"email": user.email},
                    format="json", REMOTE_ADDR="192.0.2.30",
                )
                self.assertEqual(result.status_code, 200)
                message = mail.outbox[-1]
                self.assertEqual(message.to, [user.email])
                link = re.search(r"https?://\S+", message.body)
                self.assertIsNotNone(link)
                query = parse_qs(urlsplit(link.group(0)).query)
                issued_at = datetime.now() - timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1)
                with patch.object(default_token_generator, "_now", return_value=issued_at):
                    expired_token = default_token_generator.make_token(user)
                fixtures[key] = {
                    "email": user.email,
                    "uid": query["uid"][0],
                    "token": query["token"][0],
                    "expiredToken": expired_token,
                    "password": replacement_password,
                }
        setup_email_count = len(mail.outbox)
        environment = {
            **os.environ,
            "RESET_BROWSER_API_URL": f"{self.live_server_url}/api/v1",
            "RESET_BROWSER_FIXTURES": json.dumps(fixtures),
        }
        # Inherit the terminal instead of capturing pipes. On Windows, Vite's
        # descendants can hold captured pipe handles open after Playwright exits,
        # making communicate() wait until its timeout and hiding the real error.
        # With pytest -s, browser/server output is visible as it happens.
        completed = subprocess.run(
            [node, str(cli), "test", "--config=playwright.password-reset.config.ts"],
            cwd=frontend,
            env=environment,
            timeout=600,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, "Password-reset browser checks failed; see Playwright output.")
        for key, user_id in users.items():
            user = User.objects.get(pk=user_id)
            self.assertTrue(user.check_password(fixtures[key]["password"]))
            self.assertFalse(user.check_password(old_password))
        # The browser requests one known and one unknown address per project.
        # Only the known addresses should generate an email.
        self.assertEqual(len(mail.outbox), setup_email_count + 2)
        for message in mail.outbox[setup_email_count:]:
            self.assertIn(message.to[0], [fixtures[f"{project}-query"]["email"] for project in ("chromium", "mobile-chrome")])
