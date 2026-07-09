from django.urls import path

from . import views

urlpatterns = [
    path("login", views.LoginView.as_view(), name="auth-login"),
    path("refresh", views.RefreshView.as_view(), name="auth-refresh"),
    path("logout", views.LogoutView.as_view(), name="auth-logout"),
    path("me", views.MeView.as_view(), name="auth-me"),
    path("register", views.RegisterView.as_view(), name="auth-register"),
    path("check-email", views.CheckEmailView.as_view(), name="auth-check-email"),
    path("verify-email", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("resend-otp", views.ResendOTPView.as_view(), name="auth-resend-otp"),
    path("forgot-password", views.ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("verify-reset-code", views.VerifyResetCodeView.as_view(), name="auth-verify-reset-code"),
    path("reset-password", views.ResetPasswordView.as_view(), name="auth-reset-password"),
    path("accept-invite", views.AcceptInviteView.as_view(), name="auth-accept-invite"),
]
