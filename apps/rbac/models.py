from django.conf import settings
from django.db import models

from apps.accounts.models import TimeStampedModel


class ModuleGroup(models.TextChoices):
    CONTENT = "content", "Content"
    ACADEMIC = "academic", "Academic"
    EVENTS = "events", "Events"
    SYSTEM = "system", "System"


class Module(TimeStampedModel):
    """A manageable area of the platform — drives the permission-matrix rows."""

    key = models.CharField(max_length=50, unique=True)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    group = models.CharField(max_length=20, choices=ModuleGroup.choices, default=ModuleGroup.CONTENT)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "modules"
        ordering = ["sort_order", "key"]

    def __str__(self):
        return self.key


class PermissionAction(models.TextChoices):
    VIEW = "view", "View"
    CREATE = "create", "Create"
    EDIT = "edit", "Edit"
    DELETE = "delete", "Delete"
    PUBLISH = "publish", "Publish"
    APPROVE = "approve", "Approve"
    EXPORT = "export", "Export"
    IMPORT = "import", "Import"
    ASSIGN = "assign", "Assign"
    ARCHIVE = "archive", "Archive"
    RESTORE = "restore", "Restore"


class Permission(TimeStampedModel):
    """One matrix cell: <module>.<action>. Guarded cells are Super-Admin-grantable only."""

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="permissions")
    action = models.CharField(max_length=20, choices=PermissionAction.choices)
    is_guarded = models.BooleanField(default=False)
    depends_on = models.JSONField(default=list, blank=True)  # list of "module.action" codes

    class Meta:
        db_table = "permissions"
        constraints = [
            models.UniqueConstraint(fields=["module", "action"], name="uniq_permission_module_action"),
        ]

    def __str__(self):
        return self.code

    @property
    def code(self):
        return f"{self.module.key}.{self.action}"


class Role(TimeStampedModel):
    slug = models.SlugField(max_length=60, unique=True)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "roles"

    def __str__(self):
        return self.slug


class RolePermission(TimeStampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permission_links")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_links")

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uniq_role_permission"),
        ]


class UserRole(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments"
    )
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, related_name="assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Reserved for scoped delegation, e.g. {"diocese_id": "..."} (spec Part 4 §7).
    scope = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "user_roles"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role"),
        ]
