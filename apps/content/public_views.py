"""Public content APIs — published items only, no auth."""

from collections import Counter

from django.db.models import Count, F
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Article, Event, PublishStatus
from .serializers import ArticleDetailSerializer, ArticleListSerializer, EventSerializer


class PublicCursorPagination(CursorPagination):
    page_size = 12
    ordering = "-published_at"


class ArticlesPageNumberPagination(PageNumberPagination):
    page_size = 9
    page_size_query_param = "page_size"
    max_page_size = 24


SORT_MAP = {
    "newest": "-published_at",
    "oldest": "published_at",
    "popular": "-views",
    "most_viewed": "-views",
    "updated": "-updated_at",
    "alphabetical": "title_ar",
}

READING_BUCKETS = {  # value → (min_minutes, max_minutes|None)
    "short": (0, 5),
    "medium": (5, 12),
    "long": (12, None),
}


def _published_articles():
    return Article.objects.filter(status=PublishStatus.PUBLISHED).select_related(
        "category", "cover", "author"
    )


def _apply_filters(qs, params):
    if q := params.get("q"):
        from django.db.models import Q

        qs = qs.filter(
            Q(title_ar__icontains=q) | Q(title_en__icontains=q)
            | Q(excerpt_ar__icontains=q) | Q(excerpt_en__icontains=q)
        )
    if category := params.get("category"):
        qs = qs.filter(category__slug=category)
    if author := params.get("author"):
        qs = qs.filter(author_id=author)
    if year := params.get("year"):
        if year.isdigit():
            qs = qs.filter(published_at__year=int(year))
    if tag := params.get("tag"):
        qs = qs.filter(tags__contains=[tag])
    if params.get("featured") in ("1", "true"):
        qs = qs.filter(is_featured=True)
    return qs


def _apply_reading_time(articles, bucket):
    """Reading time is computed from body length, so filter in Python."""
    if bucket not in READING_BUCKETS:
        return articles
    lo, hi = READING_BUCKETS[bucket]
    out = []
    for a in articles:
        minutes = ArticleListSerializer().get_reading_minutes(a)
        if minutes >= lo and (hi is None or minutes < hi):
            out.append(a)
    return out


class PublicArticlesView(APIView):
    """Faceted, page-numbered article list for the Articles page.

    Returns {results, page, pages, total, facets} — facets computed over the
    filtered set (minus the facet's own dimension is out of scope; kept simple
    with counts over the published corpus for stable sidebar figures)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        params = request.query_params
        base = _published_articles()
        filtered = _apply_filters(base, params)

        sort = SORT_MAP.get(params.get("sort", "newest"), "-published_at")
        filtered = filtered.order_by(sort, "-created_at")

        reading = params.get("reading_time")
        materialized = list(filtered)
        if reading:
            materialized = _apply_reading_time(materialized, reading)

        page = max(1, int(params.get("page", 1) or 1))
        size = min(24, max(1, int(params.get("page_size", 9) or 9)))
        total = len(materialized)
        pages = max(1, (total + size - 1) // size)
        start = (page - 1) * size
        window = materialized[start:start + size]

        return Response({
            "results": ArticleListSerializer(window, many=True).data,
            "page": page,
            "pages": pages,
            "total": total,
            "facets": self._facets(base),
        })

    def _facets(self, base):
        """Sidebar/filter facets over the whole published corpus."""
        cats = (
            base.exclude(category__isnull=True)
            .values("category__slug", "category__name_ar", "category__name_en")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        authors = (
            base.exclude(author__isnull=True)
            .values("author_id", "author__first_name_ar", "author__last_name_ar", "author__full_name_en")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        years = sorted(
            {a.published_at.year for a in base if a.published_at}, reverse=True
        )
        tag_counter = Counter()
        for tags in base.values_list("tags", flat=True):
            for t in tags or []:
                tag_counter[t] += 1

        recent = base.order_by("-published_at")[:5]

        return {
            "total_articles": base.count(),
            "categories": [
                {"slug": c["category__slug"], "name_ar": c["category__name_ar"],
                 "name_en": c["category__name_en"], "count": c["count"]}
                for c in cats
            ],
            "authors": [
                {"id": str(a["author_id"]),
                 "name_ar": f"{a['author__first_name_ar']} {a['author__last_name_ar']}".strip(),
                 "name_en": a["author__full_name_en"], "count": a["count"]}
                for a in authors
            ],
            "years": years,
            "tags": [{"tag": t, "count": n} for t, n in tag_counter.most_common(20)],
            "recent": ArticleListSerializer(recent, many=True).data,
        }


class PublicFeaturedArticlesView(APIView):
    """Up to 3 featured articles; falls back to most-viewed then newest."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        base = _published_articles()
        featured = list(base.filter(is_featured=True).order_by("-published_at")[:3])
        if len(featured) < 3:
            seen = {a.id for a in featured}
            filler = base.exclude(id__in=seen).order_by("-views", "-published_at")
            featured += list(filler[: 3 - len(featured)])
        return Response({"results": ArticleListSerializer(featured, many=True).data})


class PublicArticleDetailView(RetrieveAPIView):
    serializer_class = ArticleDetailSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "slug"

    def get_queryset(self):
        return Article.objects.filter(status=PublishStatus.PUBLISHED).select_related(
            "category", "cover", "author"
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Count the read without racing (atomic F expression).
        Article.objects.filter(pk=instance.pk).update(views=F("views") + 1)
        instance.views += 1
        return Response(self.get_serializer(instance).data)


class PublicEventsView(ListAPIView):
    """Published events, soonest-first. ?scope=upcoming|past filters by date."""

    serializer_class = EventSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_queryset(self):
        from django.utils import timezone

        qs = Event.objects.filter(status=PublishStatus.PUBLISHED).select_related("cover")
        scope = self.request.query_params.get("scope")
        now = timezone.now()
        if scope == "upcoming":
            qs = qs.filter(starts_at__gte=now).order_by("starts_at")
        elif scope == "past":
            qs = qs.filter(starts_at__lt=now).order_by("-starts_at")
        else:
            qs = qs.order_by("starts_at")
        return qs


# ─── News + pages + FAQs + homepage (public) ───

from rest_framework.response import Response  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from .models import FAQ, News, Page, SiteSetting  # noqa: E402
from .serializers import (  # noqa: E402
    FAQSerializer,
    NewsDetailSerializer,
    NewsListSerializer,
    PageSerializer,
)


class PublicNewsView(ListAPIView):
    serializer_class = NewsListSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = PublicCursorPagination

    def get_queryset(self):
        return News.objects.filter(status=PublishStatus.PUBLISHED).select_related("cover")


class PublicNewsDetailView(RetrieveAPIView):
    serializer_class = NewsDetailSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "slug"

    def get_queryset(self):
        return News.objects.filter(status=PublishStatus.PUBLISHED).select_related("cover")


class PublicPageView(RetrieveAPIView):
    serializer_class = PageSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "slug"

    def get_queryset(self):
        return Page.objects.filter(status=PublishStatus.PUBLISHED)


class PublicFAQsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        faqs = FAQ.objects.filter(is_published=True)
        return Response({"faqs": FAQSerializer(faqs, many=True).data})


class PublicHomepageView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        setting = SiteSetting.objects.filter(key="homepage").first()
        return Response({"homepage": setting.value if setting else {}})


# ─── Composite homepage payload (settings + all homepage collections) ───

from apps.academics.models import Program  # noqa: E402

from .models import GalleryItem, Partner, Testimonial, Thesis  # noqa: E402
from .serializers import (  # noqa: E402
    GalleryItemSerializer,
    PartnerSerializer,
    TestimonialSerializer,
    ThesisSerializer,
)


class PublicHomeDataView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        setting = SiteSetting.objects.filter(key="homepage").first()
        settings_value = setting.value if setting and "hero" in (setting.value or {}) else {}
        programs = Program.objects.filter(is_published=True).select_related("cover")
        program_rows = [
            {
                "slug": p.slug,
                "name_ar": p.name_ar, "name_en": p.name_en,
                "description_ar": p.description_ar, "description_en": p.description_en,
                "duration_ar": p.duration_ar, "duration_en": p.duration_en,
                "enrollment_status": p.enrollment_status,
                "cover_url": p.cover.file.url if p.cover else "",
            }
            for p in programs
        ]
        return Response({
            "settings": settings_value,
            "testimonials": TestimonialSerializer(
                Testimonial.objects.filter(is_published=True), many=True).data,
            "partners": PartnerSerializer(
                Partner.objects.filter(is_published=True).select_related("logo"), many=True).data,
            "gallery": GalleryItemSerializer(
                GalleryItem.objects.filter(is_published=True).select_related("media"), many=True).data,
            "theses": ThesisSerializer(
                Thesis.objects.filter(is_published=True), many=True).data,
            "programs": program_rows,
        })
