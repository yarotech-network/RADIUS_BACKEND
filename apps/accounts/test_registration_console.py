from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from .verification import send_verification_email


class RegistrationConsoleTests(SimpleTestCase):
    @override_settings(
        REGISTRATION_EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend',
        RESEND_API_KEY='test-key-never-sent',
    )
    @patch('apps.accounts.verification.requests.post')
    def test_console_override_prints_otp_without_contacting_resend(self, post):
        output = StringIO()
        with redirect_stdout(output):
            sent = send_verification_email(SimpleNamespace(username='test', email='test@example.com', pk=1), '123456')
        self.assertTrue(sent)
        self.assertIn('[Registration OTP] Code: 123456', output.getvalue())
        self.assertIn('Your verification code is: 123456', output.getvalue())
        self.assertIn('To: test@example.com', output.getvalue())
        post.assert_not_called()

    @override_settings(REGISTRATION_EMAIL_BACKEND='')
    def test_normal_delivery_does_not_print_console_notices(self):
        from .verification import registration_console_notice
        output = StringIO()
        with redirect_stdout(output):
            registration_console_notice('should not be printed')
        self.assertEqual(output.getvalue(), '')
