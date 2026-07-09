"""Admin console user APIs (spec ADM-01/02/03, Part 4 §3).

Every mutation: permission-checked, privilege-ceiling-checked, audited.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.audit.views import AuditEntrySerializer
from apps.common.errors import ApiError
from apps.rbac.models import Role, UserRole
from apps.rbac.permissions import HasPermission, can_manage_user

from .admin_serializers import (
    AdminUserCreateSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserUpdateSerializer,
)
from .emails import send_templated
from .models import User, UserStatus, UserType
from .services import issue_invite_token, revoke_invite
from .views import _send_reset_email

INVITE_URL_TEMPLATE = "{frontend}/accept-invite?token={token}"


def _privilege_error():
    return ApiError(
        "privilege_ceiling",
        "لا تملك صلاحية التعامل مع هذا الحساب",
        "You cannot act on this account",
        status_code=status.HTTP_403_FORBIDDEN,
    )


def _scoped_users(request):
    """Non-super-admins never see admin/super_admin rows (spec ADM-01 §2)."""
    qs = User.objects.filter(deleted_at__isnull=True).prefetch_related("role_assignments__role")
    if request.user.user_type != UserType.SUPER_ADMIN:
        qs = qs.filter(user_type=UserType.STUDENT)
    return qs


def _get_target(request, user_id, *, for_write=False):
    target = _scoped_users(request).filter(id=user_id).first()
    if target is None:
        raise ApiError(
            "not_found", "المستخدم غير موجود", "User not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if for_write and not can_manage_user(request.user, target):
        raise _privilege_error()
    return target


def _assert_not_last_super_admin(target):
    if target.user_type != UserType.SUPER_ADMIN:
        return
    others = User.objects.filter(
        user_type=UserType.SUPER_ADMIN, status=UserStatus.ACTIVE, deleted_at__isnull=True
    ).exclude(id=target.id)
    if not others.exists():
        raise ApiError(
            "last_super_admin",
            "لا يمكن تعطيل آخر مدير عام في النظام",
            "The last Super Admin cannot be removed",
            status_code=status.HTTP_409_CONFLICT,
        )


def _revoke_all_sessions(user) -> int:
    revoked = 0
    for token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        revoked += created
    return revoked


def _sync_roles(request, target, roles):
    before = sorted(target.role_assignments.values_list("role__slug", flat=True))
    UserRole.objects.filter(user=target).exclude(role__in=roles).delete()
    for role in roles:
        UserRole.objects.get_or_create(user=target, role=role, defaults={"assigned_by": request.user})
    after = sorted(r.slug for r in roles)
    if before != after:
        audit(request, "user.roles_updated", module="users", target=target,
              before={"roles": before}, after={"roles": after})
        # Any assignment mutation invalidates that user's cached permission set.
        # (Cache layer arrives with Redis; recompute is per-request today.)


def _send_invite_email(request, target):
    token = issue_invite_token(target)
    from django.conf import settings

    frontend = settings.FRONTEND_LOGIN_URL.rsplit("/", 1)[0]  # strip /login
    invite_url = INVITE_URL_TEMPLATE.format(frontend=frontend, token=token)
    roles = [a.role.name_ar for a in target.role_assignments.select_related("role")]
    send_templated(target.email, "admin_invitation", {
        "first_name": target.first_name_ar,
        "inviter_name": request.user.display_name_ar or request.user.email,
        "role_name": "، ".join(roles) or "مسؤول",
        "invite_url": invite_url,
        "expires_hours": 72,
    })
    target.invitation_sent_at = timezone.now()
    target.save(update_fields=["invitation_sent_at", "updated_at"])


class UserCursorPagination(CursorPagination):
    page_size = 25
    ordering = "-created_at"


class AdminUserListCreateView(ListAPIView):
    """GET /admin/users (search + filters + cursor) · POST invite admin (ADM-01/02)."""

    serializer_class = AdminUserListSerializer
    permission_classes = [HasPermission("users.view")]
    pagination_class = UserCursorPagination

    def get_queryset(self):
        qs = _scoped_users(self.request)
        params = self.request.query_params
        if q := params.get("q"):
            qs = qs.filter(
                Q(email__icontains=q) | Q(first_name_ar__icontains=q)
                | Q(last_name_ar__icontains=q) | Q(full_name_en__icontains=q)
            )
        if user_type := params.get("type"):
            qs = qs.filter(user_type=user_type)
        if status_filter := params.get("status"):
            qs = qs.filter(status=status_filter)
        if role := params.get("role"):
            qs = qs.filter(role_assignments__role__slug=role)
        return qs.distinct()

    def post(self, request):
        # Admin accounts are created only by Super Admins (spec ADM-02 §2).
        if request.user.user_type != UserType.SUPER_ADMIN:
            raise _privilege_error()
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            target = User.objects.create_user(
                email=data["email"],
                password=None,  # unusable until the invite is accepted
                first_name_ar=data["first_name_ar"],
                last_name_ar=data["last_name_ar"],
                full_name_en=data["full_name_en"],
                phone=data.get("phone") or "",
                user_type=UserType.ADMIN,
                status=UserStatus.INVITED,
                invited_by=request.user,
                account_expires_at=data.get("account_expires_at"),
            )
            for role in data["role_ids"]:
                UserRole.objects.create(user=target, role=role, assigned_by=request.user)
        _send_invite_email(request, target)
        audit(request, "user.invited", module="users", target=target,
              after={"roles": [r.slug for r in data["role_ids"]]})
        return Response(
            AdminUserDetailSerializer(target).data, status=status.HTTP_201_CREATED
        )


class AdminUserDetailView(APIView):
    permission_classes = [HasPermission("users.view")]

    def get(self, request, user_id):
        target = _get_target(request, user_id)
        return Response(AdminUserDetailSerializer(target).data)

    def patch(self, request, user_id):
        if not HasPermission("users.edit")().has_permission(request, self):
            raise _privilege_error()
        target = _get_target(request, user_id, for_write=True)
        serializer = AdminUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        identity_fields = ["first_name_ar", "last_name_ar", "full_name_en", "phone", "account_expires_at"]
        before = {f: str(getattr(target, f) or "") for f in identity_fields if f in data}
        for field in identity_fields:
            if field in data:
                setattr(target, field, data[field])
        target.save()
        after = {f: str(getattr(target, f) or "") for f in before}
        if before != after:
            audit(request, "user.updated", module="users", target=target, before=before, after=after)

        if "role_ids" in data:
            if request.user.user_type != UserType.SUPER_ADMIN:
                raise _privilege_error()  # role assignment is guarded (users.assign)
            _sync_roles(request, target, data["role_ids"])
        # Re-fetch: the scoped queryset's role prefetch is stale after a sync.
        return Response(AdminUserDetailSerializer(_get_target(request, user_id)).data)

    def delete(self, request, user_id):
        if not HasPermission("users.delete")().has_permission(request, self):
            raise _privilege_error()
        target = _get_target(request, user_id, for_write=True)
        _assert_not_last_super_admin(target)
        target.deleted_at = timezone.now()
        target.save(update_fields=["deleted_at", "updated_at"])
        _revoke_all_sessions(target)
        audit(request, "user.deleted", module="users", target=target)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserStatusView(APIView):
    """PATCH /admin/users/{id}/status {action: activate|deactivate}."""

    permission_classes = [HasPermission("users.edit")]

    def patch(self, request, user_id):
        target = _get_target(request, user_id, for_write=True)
        action = request.data.get("action")
        if action not in ("activate", "deactivate"):
            raise ApiError("invalid_action", "إجراء غير معروف", "Unknown action", status_code=400)
        before = {"status": target.status}
        if action == "deactivate":
            _assert_not_last_super_admin(target)
            target.status = UserStatus.SUSPENDED
            target.save(update_fields=["status", "updated_at"])
            revoked = _revoke_all_sessions(target)  # signs them out immediately
            audit(request, "user.deactivated", module="users", target=target,
                  before=before, after={"status": target.status, "sessions_revoked": revoked})
            send_templated(target.email, "account_suspended", {"first_name": target.first_name_ar})
        else:
            target.status = UserStatus.ACTIVE
            target.save(update_fields=["status", "updated_at"])
            audit(request, "user.activated", module="users", target=target,
                  before=before, after={"status": target.status})
        return Response(AdminUserDetailSerializer(target).data)


class AdminUserResetPasswordView(APIView):
    """POST — emails the user a reset code; never sets a password inline."""

    permission_classes = [HasPermission("users.edit")]

    def post(self, request, user_id):
        target = _get_target(request, user_id, for_write=True)
        _send_reset_email(target)
        audit(request, "user.password_reset_sent", module="users", target=target)
        return Response({"sent": True})


class AdminUserResendInviteView(APIView):
    permission_classes = [HasPermission("users.create")]

    def post(self, request, user_id):
        target = _get_target(request, user_id, for_write=True)
        if target.status != UserStatus.INVITED:
            raise ApiError("not_invited", "هذا الحساب ليس بانتظار دعوة", "Account is not pending an invite", status_code=409)
        _send_invite_email(request, target)
        audit(request, "user.invite_resent", module="users", target=target)
        return Response({"sent": True})


class AdminUserRevokeInviteView(APIView):
    permission_classes = [HasPermission("users.create")]

    def post(self, request, user_id):
        target = _get_target(request, user_id, for_write=True)
        revoked = revoke_invite(target)
        audit(request, "user.invite_revoked", module="users", target=target,
              after={"tokens_revoked": revoked})
        return Response({"revoked": revoked})


class AdminUserActivityView(ListAPIView):
    """GET — the user's audit trail: rows where they acted or were acted upon."""

    serializer_class = AuditEntrySerializer
    permission_classes = [HasPermission("users.view")]
    pagination_class = UserCursorPagination

    def get_queryset(self):
        target = _get_target(self.request, self.kwargs["user_id"])
        return AuditLog.objects.filter(
            Q(actor_id=target.id) | Q(target_id=str(target.id))
        )


class AdminUserSessionsView(APIView):
    permission_classes = [HasPermission("users.view")]

    def get(self, request, user_id):
        target = _get_target(request, user_id)
        blacklisted = set(
            BlacklistedToken.objects.filter(token__user=target).values_list("token_id", flat=True)
        )
        sessions = [
            {
                "id": str(token.id),
                "created_at": token.created_at,
                "expires_at": token.expires_at,
                "is_current": False,
            }
            for token in OutstandingToken.objects.filter(
                user=target, expires_at__gt=timezone.now()
            ).order_by("-created_at")
            if token.id not in blacklisted
        ]
        return Response({"sessions": sessions})

    def delete(self, request, user_id):
        """No session id → revoke all (spec SESSIONS)."""
        if not HasPermission("users.edit")().has_permission(request, self):
            raise _privilege_error()
        target = _get_target(request, user_id, for_write=True)
        revoked = _revoke_all_sessions(target)
        audit(request, "user.sessions_revoked", module="users", target=target,
              after={"count": revoked})
        return Response({"revoked": revoked})


class AdminUserSessionDetailView(APIView):
    permission_classes = [HasPermission("users.edit")]

    def delete(self, request, user_id, session_id):
        target = _get_target(request, user_id, for_write=True)
        token = OutstandingToken.objects.filter(user=target, id=session_id).first()
        if token is None:
            raise ApiError("not_found", "الجلسة غير موجودة", "Session not found", status_code=404)
        BlacklistedToken.objects.get_or_create(token=token)
        audit(request, "user.session_revoked", module="users", target=target,
              after={"session": str(token.id)})
        return Response(status=status.HTTP_204_NO_CONTENT)
