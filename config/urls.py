import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok", "database": "connected"})


urlpatterns = [
    # Emergency access only — the real admin UX is the Next.js dashboard.
    # Randomize in prod via DJANGO_ADMIN_PATH (checklist §5.9).
    path(os.environ.get("DJANGO_ADMIN_PATH", "django-admin/"), admin.site.urls),
    path("api/v1/health", health),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/meta/", include("apps.academics.urls")),
    path("api/v1/admin/", include("apps.accounts.admin_urls")),
    path("api/v1/admin/", include("apps.rbac.urls")),
    path("api/v1/admin/", include("apps.audit.urls")),
    path("api/v1/admin/", include("apps.content.admin_urls")),
    path("api/v1/admin/", include("apps.academics.admin_urls")),
    path("api/v1/content/", include("apps.content.urls")),
    path("api/v1/students/", include("apps.students.urls")),
    path("api/v1/schema", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
