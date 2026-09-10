from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .registration_api import RegistrationEmailView, RegistrationVerifyView, RegistrationCreateView
from .session_api import LogoutView

urlpatterns = [
    path("auth/registration/email/", RegistrationEmailView.as_view(), name="registration-email"),
    path("auth/registration/email/verify/", RegistrationVerifyView.as_view(), name="registration-verify"),
    path("auth/registration/", RegistrationCreateView.as_view(), name="registration-create"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path(
        "auth/resend-verification/",
        views.ResendVerificationView.as_view(),
        name="resend-verification",
    ),
    path("auth/user/", views.CurrentUserView.as_view(), name="current-user"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="change-password"),
    path("auth/password-reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
