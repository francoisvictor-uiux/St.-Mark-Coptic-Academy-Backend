from django.db import models

from apps.accounts.models import TimeStampedModel


class Diocese(TimeStampedModel):
    name_ar = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150)
    country_code = models.CharField(max_length=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "dioceses"
        ordering = ["country_code", "name_ar"]

    def __str__(self):
        return self.name_en


class Church(TimeStampedModel):
    diocese = models.ForeignKey(Diocese, on_delete=models.CASCADE, related_name="churches")
    name_ar = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150)
    city = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)
    # Escape-hatch entries typed by students ("أخرى"), pending admin review.
    is_user_submitted = models.BooleanField(default=False)

    class Meta:
        db_table = "churches"
        ordering = ["name_ar"]

    def __str__(self):
        return self.name_en


class EnrollmentStatus(models.TextChoices):
    OPEN = "open", "مفتوح للتسجيل"
    SOON = "soon", "قريبًا"
    CLOSED = "closed", "مغلق"


class Program(TimeStampedModel):
    slug = models.SlugField(max_length=80, unique=True)
    name_ar = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150)
    description_ar = models.TextField(blank=True, default="")
    description_en = models.TextField(blank=True, default="")
    duration_ar = models.CharField(max_length=100, blank=True, default="")
    duration_en = models.CharField(max_length=100, blank=True, default="")
    enrollment_status = models.CharField(
        max_length=10, choices=EnrollmentStatus.choices, default=EnrollmentStatus.OPEN
    )
    cover = models.ForeignKey(
        "content.MediaAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    class Meta:
        db_table = "programs"
        ordering = ["sort_order", "name_ar"]

    def __str__(self):
        return self.slug
