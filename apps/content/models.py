"""CMS content models: categories, media, articles, events.

Bilingual: Arabic required, English optional (public /en falls back to Arabic).
Publishing lifecycle: draft → published → archived.
"""

from django.conf import settings
from django.db import models

from apps.accounts.models import TimeStampedModel


class PublishStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class Category(TimeStampedModel):
    slug = models.SlugField(max_length=80, unique=True, allow_unicode=True)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "content_categories"
        ordering = ["name_ar"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.slug


def media_upload_path(instance, filename):
    return f"library/{instance.created_at:%Y/%m}/{filename}" if instance.created_at else f"library/{filename}"


class MediaAsset(TimeStampedModel):
    """Re-encoded, EXIF-stripped image in the media library (spec Part 4 §5.6)."""

    file = models.ImageField(upload_to="library/%Y/%m/")
    original_name = models.CharField(max_length=255)
    mime = models.CharField(max_length=50)
    size_bytes = models.BigIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    alt_ar = models.CharField(max_length=255, blank=True, default="")
    alt_en = models.CharField(max_length=255, blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "media_assets"
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name


class Article(TimeStampedModel):
    slug = models.SlugField(max_length=140, unique=True, allow_unicode=True)
    title_ar = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200, blank=True, default="")
    excerpt_ar = models.CharField(max_length=300, blank=True, default="")
    excerpt_en = models.CharField(max_length=300, blank=True, default="")
    body_ar = models.TextField(blank=True, default="")  # sanitized HTML
    body_en = models.TextField(blank=True, default="")  # sanitized HTML
    cover = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="articles"
    )
    status = models.CharField(
        max_length=12, choices=PublishStatus.choices, default=PublishStatus.DRAFT
    )
    is_featured = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)  # list of free-text strings
    views = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="articles"
    )

    class Meta:
        db_table = "articles"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["status", "is_featured"]),
        ]

    def __str__(self):
        return self.slug


class News(TimeStampedModel):
    slug = models.SlugField(max_length=140, unique=True, allow_unicode=True)
    title_ar = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200, blank=True, default="")
    excerpt_ar = models.CharField(max_length=300, blank=True, default="")
    excerpt_en = models.CharField(max_length=300, blank=True, default="")
    body_ar = models.TextField(blank=True, default="")  # sanitized HTML
    body_en = models.TextField(blank=True, default="")
    cover = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(
        max_length=12, choices=PublishStatus.choices, default=PublishStatus.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "news"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "published_at"])]
        verbose_name_plural = "news"

    def __str__(self):
        return self.slug


class Page(TimeStampedModel):
    """Editable website page (terms, privacy, about…) — spec module `pages`."""

    slug = models.SlugField(max_length=140, unique=True, allow_unicode=True)
    title_ar = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200, blank=True, default="")
    body_ar = models.TextField(blank=True, default="")  # sanitized HTML
    body_en = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=12, choices=PublishStatus.choices, default=PublishStatus.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "site_pages"
        ordering = ["slug"]

    def __str__(self):
        return self.slug


class FAQ(TimeStampedModel):
    question_ar = models.CharField(max_length=300)
    question_en = models.CharField(max_length=300, blank=True, default="")
    answer_ar = models.TextField()
    answer_en = models.TextField(blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    class Meta:
        db_table = "faqs"
        ordering = ["sort_order", "created_at"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question_ar[:50]


class Testimonial(TimeStampedModel):
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True, default="")
    role_ar = models.CharField(max_length=100, blank=True, default="")
    role_en = models.CharField(max_length=100, blank=True, default="")
    quote_ar = models.TextField()
    quote_en = models.TextField(blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    class Meta:
        db_table = "testimonials"
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.name_ar


class Partner(TimeStampedModel):
    name_ar = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150, blank=True, default="")
    logo = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    url = models.URLField(blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    class Meta:
        db_table = "partners"
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.name_ar


class GalleryItem(TimeStampedModel):
    """A media-library image placed in the homepage gallery carousel."""

    media = models.ForeignKey(MediaAsset, on_delete=models.CASCADE, related_name="+")
    caption_ar = models.CharField(max_length=200, blank=True, default="")
    caption_en = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        db_table = "gallery_items"
        ordering = ["sort_order", "created_at"]


class ThesisDegree(models.TextChoices):
    MASTERS = "masters", "ماجستير"
    DOCTORATE = "doctorate", "دكتوراه"


class Thesis(TimeStampedModel):
    """Library entry (homepage strip now; full theses library later)."""

    title_ar = models.CharField(max_length=300)
    title_en = models.CharField(max_length=300, blank=True, default="")
    researcher_ar = models.CharField(max_length=150)
    researcher_en = models.CharField(max_length=150, blank=True, default="")
    degree = models.CharField(max_length=12, choices=ThesisDegree.choices)
    institution_ar = models.CharField(max_length=200, blank=True, default="")
    institution_en = models.CharField(max_length=200, blank=True, default="")
    year = models.PositiveSmallIntegerField()
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    class Meta:
        db_table = "theses"
        ordering = ["sort_order", "-year"]
        verbose_name_plural = "theses"

    def __str__(self):
        return self.title_ar[:60]


class SiteSetting(TimeStampedModel):
    """Key-value store for editable site chrome (homepage hero, …)."""

    key = models.CharField(max_length=50, unique=True)
    value = models.JSONField(default=dict)

    class Meta:
        db_table = "site_settings"

    def __str__(self):
        return self.key


class EventType(models.TextChoices):
    CONFERENCE = "conference", "مؤتمر"
    SEMINAR = "seminar", "ندوة"
    DISCUSSION = "discussion", "حلقة نقاش"


class EventCapacity(models.TextChoices):
    OPEN = "open", "التسجيل متاح"
    FULL = "full", "اكتمل العدد"
    ONLINE = "online", "أونلاين"


class Event(TimeStampedModel):
    slug = models.SlugField(max_length=140, unique=True, allow_unicode=True)
    title_ar = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200, blank=True, default="")
    description_ar = models.TextField(blank=True, default="")
    description_en = models.TextField(blank=True, default="")
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    location_ar = models.CharField(max_length=200, blank=True, default="")
    location_en = models.CharField(max_length=200, blank=True, default="")
    capacity_status = models.CharField(
        max_length=10, choices=EventCapacity.choices, default=EventCapacity.OPEN
    )
    cover = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(
        max_length=12, choices=PublishStatus.choices, default=PublishStatus.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "events"
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["status", "starts_at"])]

    def __str__(self):
        return self.slug
