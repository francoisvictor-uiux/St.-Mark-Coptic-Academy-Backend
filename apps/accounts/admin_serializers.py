"""Serializers for the admin console user APIs (spec ADM-01/02/03)."""

from rest_framework import serializers

from apps.rbac.models import Role

from .models import User, UserType


class RoleChipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "slug", "name_ar", "name_en", "is_system"]


class AdminUserListSerializer(serializers.ModelSerializer):
    name_ar = serializers.CharField(source="display_name_ar", read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name_ar", "last_name_ar", "name_ar",
            "full_name_en", "user_type", "status", "roles",
            "last_login", "created_at",
        ]

    def get_roles(self, user):
        return RoleChipSerializer(
            [assignment.role for assignment in user.role_assignments.all()], many=True
        ).data


class AdminUserDetailSerializer(AdminUserListSerializer):
    permissions = serializers.SerializerMethodField()
    invited_by_label = serializers.SerializerMethodField()

    class Meta(AdminUserListSerializer.Meta):
        fields = AdminUserListSerializer.Meta.fields + [
            "phone", "locale", "email_verified_at", "invitation_sent_at",
            "account_expires_at", "invited_by_label", "permissions", "deleted_at",
        ]

    def get_permissions(self, user) -> list[str]:
        from apps.rbac.services import get_effective_permissions

        return get_effective_permissions(user)

    def get_invited_by_label(self, user) -> str:
        return user.invited_by.email if user.invited_by else ""


class AdminUserCreateSerializer(serializers.Serializer):
    """Invite a new administrator (spec ADM-02) — the only way admins exist."""

    email = serializers.EmailField(max_length=254)
    first_name_ar = serializers.CharField(max_length=50)
    last_name_ar = serializers.CharField(max_length=50)
    full_name_en = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    role_ids = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.filter(deleted_at__isnull=True), many=True
    )
    account_expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value, deleted_at__isnull=True).exists():
            raise serializers.ValidationError("email_taken")
        return value

    def validate_role_ids(self, value):
        if not value:
            raise serializers.ValidationError("At least one role is required")
        return value


class AdminUserUpdateSerializer(serializers.Serializer):
    first_name_ar = serializers.CharField(max_length=50, required=False)
    last_name_ar = serializers.CharField(max_length=50, required=False)
    full_name_en = serializers.CharField(max_length=100, required=False)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    account_expires_at = serializers.DateTimeField(required=False, allow_null=True)
    role_ids = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.filter(deleted_at__isnull=True), many=True, required=False
    )


class SessionSerializer(serializers.Serializer):
    id = serializers.CharField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    is_current = serializers.BooleanField()
