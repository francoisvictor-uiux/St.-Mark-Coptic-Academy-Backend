"""Permission enforcement (spec Part 4 §3, Part 0 §2).

UI hides what you cannot do; these classes enforce it regardless.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.models import UserType

from .services import get_effective_permissions


def effective_permissions(request) -> set[str]:
    """Effective permission set, computed once per request."""
    cached = getattr(request, "_effective_permissions", None)
    if cached is None:
        cached = set(get_effective_permissions(request.user))
        request._effective_permissions = cached
    return cached


def has_permission_code(request, code: str) -> bool:
    if not request.user.is_authenticated:
        return False
    if request.user.user_type == UserType.SUPER_ADMIN:
        return True
    return code in effective_permissions(request)


def HasPermission(code: str):  # noqa: N802 — reads like a class in view declarations
    """Usage: permission_classes = [HasPermission("users.view")]."""

    class _HasPermission(BasePermission):
        message = f"Requires permission {code}"

        def has_permission(self, request, view):
            return has_permission_code(request, code)

    _HasPermission.__name__ = f"HasPermission_{code.replace('.', '_')}"
    return _HasPermission


class IsAdminType(BasePermission):
    """Any dashboard access requires an admin-type account."""

    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.user_type in (UserType.ADMIN, UserType.SUPER_ADMIN)
        )


def can_manage_user(actor, target) -> bool:
    """Privilege ceiling (spec Part 4 §5.7): admins never mutate admin-or-higher
    accounts; only Super Admins do — and nobody mutates themselves here."""
    if actor.id == target.id:
        return False
    if actor.user_type == UserType.SUPER_ADMIN:
        return True
    return target.user_type == UserType.STUDENT
