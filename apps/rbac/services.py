"""Effective-permission resolution (spec Part 0 §2.1, Part 4 §5.4)."""

from apps.accounts.models import UserType

from .models import Permission


def get_effective_permissions(user) -> list[str]:
    """Union of all role permissions as sorted "module.action" codes.

    Super Admin implicitly holds every active permission.
    """
    if not user or not user.is_authenticated:
        return []
    if user.user_type == UserType.SUPER_ADMIN:
        qs = Permission.objects.filter(module__is_active=True)
    else:
        qs = Permission.objects.filter(
            module__is_active=True,
            role_links__role__assignments__user=user,
            role_links__role__deleted_at__isnull=True,
        ).distinct()
    return sorted(f"{module_key}.{action}" for module_key, action in qs.values_list("module__key", "action"))
