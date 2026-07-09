import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only activity record (spec Part 3 ADM-06). Never updated or deleted by the app."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_label = models.CharField(max_length=150)  # snapshot — survives user deletion
    action = models.CharField(max_length=100)  # verb.noun, e.g. "user.deactivated"
    module = models.CharField(max_length=50, blank=True, default="")
    target_type = models.CharField(max_length=50, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    target_label = models.CharField(max_length=255, blank=True, default="")
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.actor_label}: {self.action}"
