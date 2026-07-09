from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination

from apps.rbac.permissions import HasPermission

from .models import AuditLog
from .services import audit


class AuditEntrySerializer(serializers.ModelSerializer):
    actor_id = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id", "actor_id", "actor_label", "action", "module",
            "target_type", "target_id", "target_label",
            "before", "after", "ip", "user_agent", "created_at",
        ]

    def get_actor_id(self, obj) -> str | None:
        return str(obj.actor_id) if obj.actor_id else None


class AuditCursorPagination(CursorPagination):
    page_size = 25
    ordering = "-created_at"


class AuditListView(ListAPIView):
    """GET /admin/audit?actor&module&action&q&from&to&cursor (spec ADM-06)."""

    serializer_class = AuditEntrySerializer
    permission_classes = [HasPermission("audit.view")]
    pagination_class = AuditCursorPagination

    def get_queryset(self):
        qs = AuditLog.objects.all()
        params = self.request.query_params
        if actor := params.get("actor"):
            qs = qs.filter(actor_id=actor)
        if module := params.get("module"):
            qs = qs.filter(module=module)
        if action := params.get("action"):
            qs = qs.filter(action__startswith=action)
        if q := params.get("q"):
            qs = qs.filter(target_label__icontains=q)
        if date_from := params.get("from"):
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to := params.get("to"):
            qs = qs.filter(created_at__date__lte=date_to)
        return qs

    def list(self, request, *args, **kwargs):
        # Watch-the-watchers: reading the log is itself logged (spec ADM-06 §14),
        # only on the first page to avoid noise while paginating.
        if not request.query_params.get("cursor"):
            audit(request, "audit.viewed", module="audit")
        return super().list(request, *args, **kwargs)
