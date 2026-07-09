from django.urls import path

from . import views

urlpatterns = [
    path("permissions/catalog", views.PermissionCatalogView.as_view(), name="admin-permissions-catalog"),
    path("roles", views.RoleListCreateView.as_view(), name="admin-roles"),
    path("roles/<uuid:role_id>", views.RoleDetailView.as_view(), name="admin-role-detail"),
    path("roles/<uuid:role_id>/permissions", views.RolePermissionsView.as_view(), name="admin-role-permissions"),
    path("roles/<uuid:role_id>/duplicate", views.RoleDuplicateView.as_view(), name="admin-role-duplicate"),
]
