import logging

from django.conf import settings
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils import timezone
from .serializers import (
    UserSerializer, LoginSerializer, RegisterSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ChangePasswordSerializer, VerifyEmailSerializer, ResendVerificationSerializer,
)
from .verification import (
    RESEND_COOLDOWN,
    check_code,
    issue_code,
    mark_verified,
    send_verification_email,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is not None:
            if user.email_verified_at is None and not (
                user.is_superuser or user.is_platform_admin
            ):
                return Response(
                    {
                        "error": "Verify your email address before signing in.",
                        "code": "email_not_verified",
                        # Only reachable with valid credentials, so the address is
                        # not a disclosure — it lets the sign-in page hand the user
                        # straight to the verification step.
                        "email": user.email,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
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
        # The account exists but stays locked behind email confirmation: issue the
        # OTP and withhold tokens until POST /auth/verify-email/ succeeds.
        _, code = issue_code(user)
        send_verification_email(user, code)
        return Response(
            {
                "user": UserSerializer(user).data,
                "detail": (
                    "Workspace created. A verification code has been sent to your email — "
                    "enter it to activate your account."
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    """Confirm an OTP and activate the account. Returns tokens (auto sign-in)."""

    permission_classes = [permissions.AllowAny]
    serializer_class = VerifyEmailSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email_verify"

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]

        user = User.objects.filter(email__iexact=email).first()
        if user is None or user.email_verified_at is not None:
            # Same response for unknown addresses and already-verified accounts:
            # never confirm which emails exist. Already-verified users are nudged
            # to sign in by the generic message below.
            return Response(
                {"detail": "Invalid code or email.", "code": "invalid_code_or_email"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ok, error = check_code(user, code)
        if not ok:
            return Response(
                {"detail": error, "code": "invalid_code"}, status=status.HTTP_400_BAD_REQUEST
            )

        mark_verified(user)
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        })


class ResendVerificationView(APIView):
    """Email a fresh OTP to an unverified account (generic response, no enumeration)."""

    permission_classes = [permissions.AllowAny]
    serializer_class = ResendVerificationSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email_resend"

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email__iexact=email, email_verified_at__isnull=True).first()
        sent = False
        if user is not None:
            latest = user.email_codes.order_by("-created_at").first()
            # Local cooldown so a hammering client cannot mint unlimited codes.
            if latest is not None and latest.created_at > timezone.now() - RESEND_COOLDOWN:
                sent = None  # too soon — do not issue, but keep the response generic
            else:
                _, code = issue_code(user)
                sent = send_verification_email(user, code)

        message = (
            "If an unverified account exists for that email, a new code is on its way. "
            "Codes can be resent once per minute."
        )
        if sent is None:
            message = "A code was sent recently — please wait a minute before requesting another."
        return Response({"message": message})


class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    serializer_class = ChangePasswordSerializer
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"message": "Password changed successfully."})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetRequestSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"],
            is_active=True,
        ).first()
        if user and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = settings.PASSWORD_RESET_FRONTEND_URL.format(
                uid=uid,
                token=token,
            )
            try:
                send_mail(
                    subject="Reset your Yarotech Radius password",
                    message=(
                        "A password reset was requested for your account. "
                        f"Use this link to continue:\n\n{reset_url}\n\n"
                        "If you did not request this, you can ignore this email."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception:
                # Keep the public response indistinguishable for existing and
                # unknown addresses while preserving an operator-visible error.
                logger.exception("Password reset email delivery failed")

        return Response({
            "message": "If an active account exists for that email, reset instructions have been sent."
        })


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user_id = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is None or not default_token_generator.check_token(
            user, serializer.validated_data["token"]
        ):
            return Response(
                {"error": "Invalid or expired password reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(serializer.validated_data["password"], user=user)
        except DjangoValidationError as exc:
            return Response(
                {"password": list(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        return Response({"message": "Password reset successful."})
