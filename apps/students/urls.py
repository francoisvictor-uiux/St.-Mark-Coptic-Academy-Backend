from django.urls import path

from . import views

urlpatterns = [
    path("me/profile", views.MyProfileView.as_view(), name="student-profile"),
    path("me/photo", views.MyPhotoView.as_view(), name="student-photo"),
    path("me/documents", views.MyDocumentsView.as_view(), name="student-documents"),
    path("me/documents/<uuid:document_id>", views.MyDocumentDetailView.as_view(), name="student-document"),
]
