from django.urls import path

from . import admin_views as views

urlpatterns = [
    path("programs", views.ProgramListCreateView.as_view()),
    path("programs/reorder", views.ProgramReorderView.as_view()),
    path("programs/<uuid:program_id>", views.ProgramDetailView.as_view()),
]
