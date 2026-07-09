"""RBAC admin APIs: catalog, roles CRUD, matrix save (spec ADM-04/05, Part 4 §3)."""

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserType
from apps.audit.services import audit
from apps.common.errors import ApiError

from .models import Module, Permission, Role, RolePermission, UserRole
from .permissions import HasPermission


# ─── Serializers ───

class CatalogPermissionSerializer(serializers.ModelSerializer):
    code = serializers.CharField(read_only=True)

    class Meta:
        model = Permission
        fields = ["id", "action", "code", "is_guarded", "depends_on"]


class CatalogModuleSerializer(serializers.ModelSerializer):
    permissions = CatalogPermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = ["key", "name_ar", "name_en", "group", "sort_order", "permissions"]


class RoleSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    permission_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = [
            "id", "slug", "name_ar", "name_en", "description",
            "is_system", "member_count", "permission_count", "created_at",
        ]


class RoleWriteSerializer(serializers.Serializer):
    name_ar = serializers.CharField(max_length=100)
    name_en = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


# ─── Helpers ───

def _roles_qs():
    return Role.objects.filter(deleted_at__isnull=True).annotate(
        member_count=Count("assignments", distinct=True),
        permission_count=Count("permission_links", distinct=True),
    )


def _get_role(role_id) -> Role:
    role = _roles_qs().filter(id=role_id).first()
    if role is None:
        raise ApiError("not_found", "الدور غير موجود", "Role not found", status_code=404)
    return role


def _unique_slug(base: str) -> str:
    slug = slugify(base) or "role"
    candidate, n = slug, 2
    while Role.objects.filter(slug=candidate).exists():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def _validate_dependencies(permission_ids: list) -> None:
    """Every permission's depends_on codes must be inside the submitted set."""
    perms = Permission.objects.filter(id__in=permission_ids).select_related("module")
    selected_codes = {p.code for p in perms}
    violations = []
    for perm in perms:
        for required in perm.depends_on:
            if required not in selected_codes:
                violations.append({"permission": perm.code, "requires": required})
    if violations:
        raise ApiError(
            "dependency_violation",
            "بعض الصلاحيات تتطلب صلاحيات أخرى غير محددة",
            "Some permissions require others that are not selected",
            status_code=422,
            fields={"dependencies": violations},
        )


# ─── Views ───

class PermissionCatalogView(APIView):
    """GET /admin/permissions/catalog — feeds the matrix grid (spec ADM-05)."""

    permission_classes = [HasPermission("roles.view")]

    def get(self, request):
        modules = Module.objects.filter(is_active=True).prefetch_related("permissions")
        return Response({"modules": CatalogModuleSerializer(modules, many=True).data})


class RoleListCreateView(APIView):
    permission_classes = [HasPermission("roles.view")]

    def get(self, request):
        roles = _roles_qs().order_by("created_at")
        data = RoleSerializer(roles, many=True).data
        if request.query_params.get("with") == "permissions":
            links = RolePermission.objects.select_related("permission__module")
            by_role: dict = {}
            for link in links:
                by_role.setdefault(str(link.role_id), []).append(str(link.permission_id))
            for row in data:
                row["permission_ids"] = by_role.get(row["id"], [])
        return Response({"roles": data})

    def post(self, request):
        if not HasPermission("roles.create")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية إنشاء الأدوار", "Missing roles.create", status_code=403)
        serializer = RoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        role = Role.objects.create(
            slug=_unique_slug(data["name_en"]),
            name_ar=data["name_ar"],
            name_en=data["name_en"],
            description=data.get("description", ""),
            created_by=request.user,
        )
        audit(request, "role.created", module="roles", target=role)
        role = _get_role(role.id)
        return Response(RoleSerializer(role).data, status=status.HTTP_201_CREATED)


class RoleDetailView(APIView):
    permission_classes = [HasPermission("roles.view")]

    def get(self, request, role_id):
        role = _get_role(role_id)
        permission_ids = list(
            RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
        )
        data = RoleSerializer(role).data
        data["permission_ids"] = [str(pk) for pk in permission_ids]
        return Response(data)

    def patch(self, request, role_id):
        if not HasPermission("roles.edit")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية تعديل الأدوار", "Missing roles.edit", status_code=403)
        role = _get_role(role_id)
        if role.is_system:
            raise ApiError("system_role", "أدوار النظام غير قابلة للتعديل", "System roles cannot be edited", status_code=403)
        serializer = RoleWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = {"name_ar": role.name_ar, "name_en": role.name_en, "description": role.description}
        for field, value in serializer.validated_data.items():
            setattr(role, field, value)
        role.save()
        audit(request, "role.updated", module="roles", target=role, before=before,
              after={"name_ar": role.name_ar, "name_en": role.name_en, "description": role.description})
        return Response(RoleSerializer(_get_role(role.id)).data)

    def delete(self, request, role_id):
        if not HasPermission("roles.delete")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية حذف الأدوار", "Missing roles.delete", status_code=403)
        role = _get_role(role_id)
        if role.is_system:
            raise ApiError("system_role", "أدوار النظام غير قابلة للحذف", "System roles cannot be deleted", status_code=403)
        members = UserRole.objects.filter(role=role).select_related("user")
        if members.exists():
            return Response(
                {
                    "error": {
                        "code": "role_occupied",
                        "message_ar": "لا يمكن حذف دور لديه أعضاء — انقلهم أولًا",
                        "message_en": "Role has members — reassign them first",
                        "fields": {},
                    },
                    "members": [
                        {"id": str(m.user.id), "email": m.user.email, "name_ar": m.user.display_name_ar}
                        for m in members[:20]
                    ],
                },
                status=status.HTTP_409_CONFLICT,
            )
        role.deleted_at = timezone.now()
        role.save(update_fields=["deleted_at", "updated_at"])
        audit(request, "role.deleted", module="roles", target=role)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RolePermissionsView(APIView):
    """PUT /admin/roles/{id}/permissions {permission_ids[]} — the matrix save."""

    permission_classes = [HasPermission("roles.edit")]

    def put(self, request, role_id):
        role = _get_role(role_id)
        if role.is_system:
            raise ApiError("system_role", "أدوار النظام غير قابلة للتعديل", "System roles cannot be edited", status_code=403)
        permission_ids = request.data.get("permission_ids", [])
        if not isinstance(permission_ids, list):
            raise ApiError("invalid_payload", "حمولة غير صالحة", "permission_ids must be a list", status_code=400)

        perms = list(Permission.objects.filter(id__in=permission_ids).select_related("module"))
        if len(perms) != len(set(permission_ids)):
            raise ApiError("unknown_permission", "صلاحية غير معروفة", "Unknown permission id", status_code=422)

        # Guarded permissions grantable only by Super Admins (spec §2.2 rules).
        if request.user.user_type != UserType.SUPER_ADMIN:
            current = set(RolePermission.objects.filter(role=role).values_list("permission_id", flat=True))
            newly_granted_guarded = [p.code for p in perms if p.is_guarded and p.id not in current]
            if newly_granted_guarded:
                raise ApiError(
                    "guarded_permission",
                    "هذه الصلاحيات يمنحها المدير العام فقط",
                    "Only a Super Admin can grant guarded permissions",
                    status_code=403,
                    fields={"guarded": newly_granted_guarded},
                )
            # Self-lockout guard (spec ADM-05 §7): cannot strip your own roles.edit.
            actor_role_ids = set(
                UserRole.objects.filter(user=request.user).values_list("role_id", flat=True)
            )
            new_codes = {p.code for p in perms}
            if role.id in actor_role_ids and "roles.edit" not in new_codes:
                raise ApiError(
                    "self_lockout",
                    "لا يمكنك إزالة صلاحية تعديل الأدوار من دورك أنت",
                    "You cannot remove roles.edit from your own role",
                    status_code=422,
                )

        _validate_dependencies(permission_ids)

        with transaction.atomic():
            before_ids = set(
                RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
            )
            after_ids = {p.id for p in perms}
            RolePermission.objects.filter(role=role).exclude(permission_id__in=after_ids).delete()
            for perm in perms:
                if perm.id not in before_ids:
                    RolePermission.objects.create(role=role, permission=perm)

        code_of = {p.id: p.code for p in Permission.objects.filter(
            id__in=before_ids | after_ids).select_related("module")}
        added = sorted(code_of[pk] for pk in after_ids - before_ids)
        removed = sorted(code_of[pk] for pk in before_ids - after_ids)
        affected_users = UserRole.objects.filter(role=role).count()
        if added or removed:
            audit(request, "role.permissions_updated", module="roles", target=role,
                  before={"removed": removed}, after={"added": added})
        return Response({"added": added, "removed": removed, "affected_users": affected_users})


class RoleDuplicateView(APIView):
    permission_classes = [HasPermission("roles.create")]

    def post(self, request, role_id):
        source = _get_role(role_id)
        copy = Role.objects.create(
            slug=_unique_slug(f"{source.slug}-copy"),
            name_ar=f"نسخة من {source.name_ar}",
            name_en=f"Copy of {source.name_en}",
            description=source.description,
            created_by=request.user,
        )
        RolePermission.objects.bulk_create([
            RolePermission(role=copy, permission_id=link.permission_id)
            for link in RolePermission.objects.filter(role=source)
        ])
        audit(request, "role.duplicated", module="roles", target=copy,
              before={"source": source.slug})
        return Response(RoleSerializer(_get_role(copy.id)).data, status=status.HTTP_201_CREATED)
