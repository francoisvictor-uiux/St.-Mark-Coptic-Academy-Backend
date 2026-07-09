from django.conf import settings
from django.db import models

from apps.accounts.models import TimeStampedModel


class Gender(models.TextChoices):
    MALE = "male", "ذكر"
    FEMALE = "female", "أنثى"


class EducationLevel(models.TextChoices):
    SECONDARY = "secondary", "ثانوي"
    BACHELOR = "bachelor", "بكالوريوس"
    MASTER = "master", "ماجستير"
    DOCTORATE = "doctorate", "دكتوراه"
    OTHER = "other", "أخرى"


class StudentProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile"
    )
    country_code = models.CharField(max_length=2, blank=True, default="")
    diocese = models.ForeignKey(
        "academics.Diocese", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    church = models.ForeignKey(
        "academics.Church", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    church_other_text = models.CharField(max_length=150, blank=True, default="")
    program_interest = models.ForeignKey(
        "academics.Program", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    photo = models.FileField(upload_to="avatars/", null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    nationality_code = models.CharField(max_length=2, blank=True, default="")
    education_level = models.CharField(
        max_length=20, choices=EducationLevel.choices, blank=True, default=""
    )
    education_field = models.CharField(max_length=120, blank=True, default="")
    church_service = models.CharField(max_length=120, blank=True, default="")
    confession_father = models.CharField(max_length=120, blank=True, default="")
    bio = models.CharField(max_length=500, blank=True, default="")
    emergency_name = models.CharField(max_length=120, blank=True, default="")
    emergency_relation = models.CharField(max_length=60, blank=True, default="")
    emergency_phone = models.CharField(max_length=20, blank=True, default="")
    completion_pct = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "student_profiles"

    def __str__(self):
        return f"profile:{self.user_id}"


class StudentDocument(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.FileField(upload_to="documents/")
    original_name = models.CharField(max_length=255)
    mime = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField(default=0)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "student_documents"
