"""Serializers for CMS admin + public APIs."""

import secrets

from django.utils.text import slugify
from rest_framework import serializers

from .models import FAQ, Article, Category, Event, MediaAsset, News, Page
from .services import sanitize_html


class CategorySerializer(serializers.ModelSerializer):
    article_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ["id", "slug", "name_ar", "name_en", "is_active", "article_count"]
        read_only_fields = ["slug"]


class MediaSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            "id", "url", "original_name", "mime", "size_bytes",
            "width", "height", "alt_ar", "alt_en", "created_at",
        ]

    def get_url(self, obj) -> str:
        return obj.file.url  # relative /media/... — proxied by Next in dev/prod


def unique_slug(model, title_en: str, title_ar: str, provided: str = "") -> str:
    base = provided.strip() or slugify(title_en) or slugify(title_ar, allow_unicode=True)
    if not base:
        base = secrets.token_hex(4)
    candidate, n = base, 2
    while model.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


class ArticleListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    cover = MediaSerializer(read_only=True)
    author_label = serializers.SerializerMethodField()
    reading_minutes = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            "id", "slug", "title_ar", "title_en", "excerpt_ar", "excerpt_en",
            "category", "cover", "status", "is_featured", "tags", "views",
            "published_at", "author_label", "reading_minutes", "created_at", "updated_at",
        ]

    def get_author_label(self, obj) -> str:
        return obj.author.display_name_ar if obj.author else ""

    def get_reading_minutes(self, obj) -> int:
        from django.utils.html import strip_tags

        words = len(strip_tags(obj.body_ar or obj.body_en).split())
        return max(1, round(words / 180))


class ArticleDetailSerializer(ArticleListSerializer):
    class Meta(ArticleListSerializer.Meta):
        fields = ArticleListSerializer.Meta.fields + ["body_ar", "body_en"]


class ArticleWriteSerializer(serializers.Serializer):
    title_ar = serializers.CharField(max_length=200)
    title_en = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    slug = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    excerpt_ar = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    excerpt_en = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    body_ar = serializers.CharField(required=False, allow_blank=True, default="")
    body_en = serializers.CharField(required=False, allow_blank=True, default="")
    cover_id = serializers.PrimaryKeyRelatedField(
        source="cover", queryset=MediaAsset.objects.all(), required=False, allow_null=True, default=None
    )
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=Category.objects.filter(is_active=True),
        required=False, allow_null=True, default=None,
    )
    is_featured = serializers.BooleanField(required=False)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, default=list
    )

    def validate_body_ar(self, value):
        return sanitize_html(value)

    def validate_body_en(self, value):
        return sanitize_html(value)

    def validate_tags(self, value):
        # De-dupe, trim, cap at 8 tags.
        seen, out = set(), []
        for tag in value:
            t = tag.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out[:8]


class NewsListSerializer(serializers.ModelSerializer):
    cover = MediaSerializer(read_only=True)

    class Meta:
        model = News
        fields = [
            "id", "slug", "title_ar", "title_en", "excerpt_ar", "excerpt_en",
            "cover", "status", "published_at", "created_at", "updated_at",
        ]


class NewsDetailSerializer(NewsListSerializer):
    class Meta(NewsListSerializer.Meta):
        fields = NewsListSerializer.Meta.fields + ["body_ar", "body_en"]


class NewsWriteSerializer(serializers.Serializer):
    title_ar = serializers.CharField(max_length=200)
    title_en = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    slug = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    excerpt_ar = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    excerpt_en = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    body_ar = serializers.CharField(required=False, allow_blank=True, default="")
    body_en = serializers.CharField(required=False, allow_blank=True, default="")
    cover_id = serializers.PrimaryKeyRelatedField(
        source="cover", queryset=MediaAsset.objects.all(), required=False, allow_null=True, default=None
    )

    def validate_body_ar(self, value):
        return sanitize_html(value)

    def validate_body_en(self, value):
        return sanitize_html(value)


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = [
            "id", "slug", "title_ar", "title_en", "body_ar", "body_en",
            "status", "published_at", "created_at", "updated_at",
        ]


class PageWriteSerializer(serializers.Serializer):
    title_ar = serializers.CharField(max_length=200)
    title_en = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    slug = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    body_ar = serializers.CharField(required=False, allow_blank=True, default="")
    body_en = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_body_ar(self, value):
        return sanitize_html(value)

    def validate_body_en(self, value):
        return sanitize_html(value)


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = [
            "id", "question_ar", "question_en", "answer_ar", "answer_en",
            "sort_order", "is_published", "created_at",
        ]


class EventSerializer(serializers.ModelSerializer):
    cover = MediaSerializer(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id", "slug", "title_ar", "title_en", "description_ar", "description_en",
            "event_type", "starts_at", "ends_at", "location_ar", "location_en",
            "capacity_status", "cover", "status", "published_at", "created_at", "updated_at",
        ]


class EventWriteSerializer(serializers.Serializer):
    title_ar = serializers.CharField(max_length=200)
    title_en = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    slug = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    description_ar = serializers.CharField(required=False, allow_blank=True, default="")
    description_en = serializers.CharField(required=False, allow_blank=True, default="")
    event_type = serializers.ChoiceField(choices=["conference", "seminar", "discussion"])
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    location_ar = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    location_en = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    capacity_status = serializers.ChoiceField(choices=["open", "full", "online"], default="open")
    cover_id = serializers.PrimaryKeyRelatedField(
        source="cover", queryset=MediaAsset.objects.all(), required=False, allow_null=True, default=None
    )

    def validate(self, attrs):
        ends = attrs.get("ends_at")
        if ends and ends <= attrs["starts_at"]:
            raise serializers.ValidationError({"ends_at": ["must be after starts_at"]})
        return attrs


# ─── Homepage collections ───

from .models import GalleryItem, Partner, Testimonial, Thesis  # noqa: E402


class TestimonialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Testimonial
        fields = [
            "id", "name_ar", "name_en", "role_ar", "role_en",
            "quote_ar", "quote_en", "sort_order", "is_published", "created_at",
        ]
        read_only_fields = ["sort_order"]


class PartnerSerializer(serializers.ModelSerializer):
    logo = MediaSerializer(read_only=True)
    logo_id = serializers.PrimaryKeyRelatedField(
        source="logo", queryset=MediaAsset.objects.all(),
        required=False, allow_null=True, default=None, write_only=True,
    )

    class Meta:
        model = Partner
        fields = [
            "id", "name_ar", "name_en", "logo", "logo_id", "url",
            "sort_order", "is_published", "created_at",
        ]
        read_only_fields = ["sort_order"]


class GalleryItemSerializer(serializers.ModelSerializer):
    media = MediaSerializer(read_only=True)
    media_id = serializers.PrimaryKeyRelatedField(
        source="media", queryset=MediaAsset.objects.all(), write_only=True,
    )

    class Meta:
        model = GalleryItem
        fields = [
            "id", "media", "media_id", "caption_ar", "caption_en",
            "sort_order", "is_published", "created_at",
        ]
        read_only_fields = ["sort_order"]


class ThesisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Thesis
        fields = [
            "id", "title_ar", "title_en", "researcher_ar", "researcher_en",
            "degree", "institution_ar", "institution_en", "year",
            "sort_order", "is_published", "created_at",
        ]
        read_only_fields = ["sort_order"]
