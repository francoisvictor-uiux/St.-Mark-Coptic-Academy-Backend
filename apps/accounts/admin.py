from django.contrib import admin

from .models import EmailLog, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "user_type", "status", "created_at", "last_login")
    list_filter = ("user_type", "status")
    search_fields = ("email", "full_name_en", "first_name_ar", "last_name_ar")
    ordering = ("-created_at",)
    readonly_fields = ("password",)


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """Read-only send audit trail — interim 'email failures' view (spec Part 4 §4)."""

    list_display = ("created_at", "status", "template", "to_email", "subject")
    list_filter = ("status", "template")
    search_fields = ("to_email", "subject")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
