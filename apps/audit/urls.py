from django.urls import path

from . import views

urlpatterns = [
    path("audit", views.AuditListView.as_view(), name="admin-audit"),
]
