from django.urls import path

from . import admin_views as views

urlpatterns = [
    path("users", views.AdminUserListCreateView.as_view(), name="admin-users"),
    path("users/<uuid:user_id>", views.AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("users/<uuid:user_id>/status", views.AdminUserStatusView.as_view(), name="admin-user-status"),
    path("users/<uuid:user_id>/reset-password", views.AdminUserResetPasswordView.as_view(), name="admin-user-reset"),
    path("users/<uuid:user_id>/resend-invite", views.AdminUserResendInviteView.as_view(), name="admin-user-resend-invite"),
    path("users/<uuid:user_id>/revoke-invite", views.AdminUserRevokeInviteView.as_view(), name="admin-user-revoke-invite"),
    path("users/<uuid:user_id>/activity", views.AdminUserActivityView.as_view(), name="admin-user-activity"),
    path("users/<uuid:user_id>/sessions", views.AdminUserSessionsView.as_view(), name="admin-user-sessions"),
    path("users/<uuid:user_id>/sessions/<int:session_id>", views.AdminUserSessionDetailView.as_view(), name="admin-user-session"),
]
