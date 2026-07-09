"""Append-only audit writing (spec Part 3 ADM-06, Part 4 §2).

Usage:
    from apps.audit.services import audit
    audit(request, "user.deactivated", module="users", target=user,
          before={"status": "active"}, after={"status": "suspended"})
"""

import logging

from .models import AuditLog

logger = logging.getLogger(__name__)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _label_for(obj) -> str:
    for attr in ("email", "slug", "name_en", "name_ar"):
        value = getattr(obj, attr, None)
        if value:
            return str(value)
    return str(obj)


def audit(request, action: str, *, module: str = "", target=None,
          target_type: str = "", target_id: str = "", target_label: str = "",
          before=None, after=None) -> None:
    """Write one audit row. Never raises — auditing must not break the action."""
    try:
        actor = request.user if request.user.is_authenticated else None
        if target is not None:
            target_type = target_type or type(target).__name__.lower()
            target_id = target_id or str(getattr(target, "id", ""))
            target_label = target_label or _label_for(target)
        AuditLog.objects.create(
            actor=actor,
            actor_label=(actor.email if actor else "anonymous"),
            action=action,
            module=module,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            before=before,
            after=after,
            ip=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        )
    except Exception:
        logger.exception("audit write failed: action=%s", action)
