from django.urls import path

from . import views

urlpatterns = [
    path(
        "registration-options",
        views.RegistrationOptionsView.as_view(),
        name="meta-registration-options",
    ),
]
