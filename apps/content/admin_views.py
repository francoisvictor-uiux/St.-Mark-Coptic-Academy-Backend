"""CMS admin APIs — permission-enforced (RBAC matrix) and audited."""

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import audit
from apps.common.errors import ApiError
from apps.rbac.permissions import HasPermission

from .models import Article, Category, Event, MediaAsset, PublishStatus
from .serializers import (
    ArticleDetailSerializer,
    ArticleListSerializer,
    ArticleWriteSerializer,
    CategorySerializer,
    EventSerializer,
    EventWriteSerializer,
    MediaSerializer,
    unique_slug,
)
from .services import process_image


class ContentCursorPagination(CursorPagination):
    page_size = 24
    ordering = "-created_at"


def _not_found(what="العنصر"):
    return ApiError("not_found", f"{what} غير موجود", "Not found", status_code=404)


# ─── Categories ───

class CategoryListCreateView(APIView):
    permission_classes = [HasPermission("categories.view")]

    def get(self, request):
        categories = Category.objects.annotate(article_count=Count("articles")).order_by("name_ar")
        return Response({"categories": CategorySerializer(categories, many=True).data})

    def post(self, request):
        if not HasPermission("categories.create")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing categories.create", status_code=403)
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = Category.objects.create(
            slug=unique_slug(Category, serializer.validated_data.get("name_en", ""),
                             serializer.validated_data["name_ar"]),
            **serializer.validated_data,
        )
        audit(request, "category.created", module="categories", target=category)
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    permission_classes = [HasPermission("categories.edit")]

    def patch(self, request, category_id):
        category = Category.objects.filter(id=category_id).first()
        if category is None:
            raise _not_found("التصنيف")
        serializer = CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(request, "category.updated", module="categories", target=category)
        return Response(serializer.data)

    def delete(self, request, category_id):
        if not HasPermission("categories.delete")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing categories.delete", status_code=403)
        category = Category.objects.filter(id=category_id).first()
        if category is None:
            raise _not_found("التصنيف")
        audit(request, "category.deleted", module="categories", target=category)
        category.delete()  # articles keep living: FK is SET_NULL
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Media ───

class MediaListCreateView(ListAPIView):
    serializer_class = MediaSerializer
    permission_classes = [HasPermission("media.view")]
    pagination_class = ContentCursorPagination
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        qs = MediaAsset.objects.all()
        if q := self.request.query_params.get("q"):
            qs = qs.filter(Q(original_name__icontains=q) | Q(alt_ar__icontains=q))
        return qs

    def post(self, request):
        if not HasPermission("media.create")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing media.create", status_code=403)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ApiError("missing_file", "أرفق ملف صورة", "Attach an image file", status_code=400)
        content, width, height, mime, _ = process_image(uploaded)
        asset = MediaAsset.objects.create(
            file=content,
            original_name=uploaded.name[:255],
            mime=mime,
            size_bytes=content.size,
            width=width,
            height=height,
            alt_ar=request.data.get("alt_ar", "")[:255],
            alt_en=request.data.get("alt_en", "")[:255],
            uploaded_by=request.user,
        )
        audit(request, "media.uploaded", module="media", target=asset,
              after={"name": asset.original_name, "size": asset.size_bytes})
        return Response(MediaSerializer(asset).data, status=status.HTTP_201_CREATED)


class MediaDetailView(APIView):
    permission_classes = [HasPermission("media.edit")]

    def patch(self, request, media_id):
        asset = MediaAsset.objects.filter(id=media_id).first()
        if asset is None:
            raise _not_found("الملف")
        for field in ("alt_ar", "alt_en"):
            if field in request.data:
                setattr(asset, field, str(request.data[field])[:255])
        asset.save()
        return Response(MediaSerializer(asset).data)

    def delete(self, request, media_id):
        if not HasPermission("media.delete")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing media.delete", status_code=403)
        asset = MediaAsset.objects.filter(id=media_id).first()
        if asset is None:
            raise _not_found("الملف")
        audit(request, "media.deleted", module="media", target=asset,
              before={"name": asset.original_name})
        asset.file.delete(save=False)
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Generic publishable content (articles + events share the lifecycle) ───

class _BaseContentList(ListAPIView):
    model = None
    write_serializer = None
    detail_serializer = None
    module = ""
    pagination_class = ContentCursorPagination

    def filtered(self):
        qs = self.model.objects.select_related("cover").all()
        params = self.request.query_params
        if status_filter := params.get("status"):
            qs = qs.filter(status=status_filter)
        if q := params.get("q"):
            qs = qs.filter(Q(title_ar__icontains=q) | Q(title_en__icontains=q))
        return qs

    def create_extra(self, data):
        return {}

    def post(self, request):
        if not HasPermission(f"{self.module}.create")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", f"Missing {self.module}.create", status_code=403)
        serializer = self.write_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        provided_slug = data.pop("slug", "")
        obj = self.model.objects.create(
            slug=unique_slug(self.model, data.get("title_en", ""), data["title_ar"], provided_slug),
            author=request.user,
            **data,
        )
        audit(request, f"{self.module[:-1] if self.module.endswith('s') else self.module}.created",
              module=self.module, target=obj)
        return Response(self.detail_serializer(obj).data, status=status.HTTP_201_CREATED)


class _BaseContentDetail(APIView):
    model = None
    write_serializer = None
    detail_serializer = None
    module = ""

    def _get(self, object_id):
        obj = self.model.objects.filter(id=object_id).first()
        if obj is None:
            raise _not_found()
        return obj

    def get(self, request, object_id):
        return Response(self.detail_serializer(self._get(object_id)).data)

    def patch(self, request, object_id):
        if not HasPermission(f"{self.module}.edit")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", f"Missing {self.module}.edit", status_code=403)
        obj = self._get(object_id)
        serializer = self.write_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        new_slug = data.pop("slug", None)
        if new_slug and new_slug != obj.slug:
            obj.slug = unique_slug(self.model, "", "", new_slug)
        for field, value in data.items():
            setattr(obj, field, value)
        obj.save()
        audit(request, f"{self._verb()}.updated", module=self.module, target=obj)
        return Response(self.detail_serializer(obj).data)

    def delete(self, request, object_id):
        if not HasPermission(f"{self.module}.delete")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", f"Missing {self.module}.delete", status_code=403)
        obj = self._get(object_id)
        audit(request, f"{self._verb()}.deleted", module=self.module, target=obj)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _verb(self):
        return self.module[:-1] if self.module.endswith("s") else self.module


class _BasePublishView(APIView):
    model = None
    detail_serializer = None
    module = ""

    def post(self, request, object_id, action):
        if not HasPermission(f"{self.module}.publish")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية النشر", f"Missing {self.module}.publish", status_code=403)
        obj = self.model.objects.filter(id=object_id).first()
        if obj is None:
            raise _not_found()
        verb = self.module[:-1] if self.module.endswith("s") else self.module
        before = {"status": obj.status}
        if action == "publish":
            obj.status = PublishStatus.PUBLISHED
            obj.published_at = obj.published_at or timezone.now()
            audit_action = f"{verb}.published"
        elif action == "unpublish":
            obj.status = PublishStatus.DRAFT
            audit_action = f"{verb}.unpublished"
        elif action == "archive":
            obj.status = PublishStatus.ARCHIVED
            audit_action = f"{verb}.archived"
        else:
            raise ApiError("invalid_action", "إجراء غير معروف", "Unknown action", status_code=400)
        obj.save(update_fields=["status", "published_at", "updated_at"])
        audit(request, audit_action, module=self.module, target=obj,
              before=before, after={"status": obj.status})
        return Response(self.detail_serializer(obj).data)


# ─── Articles ───

class ArticleListCreateView(_BaseContentList):
    model = Article
    write_serializer = ArticleWriteSerializer
    detail_serializer = ArticleDetailSerializer
    serializer_class = ArticleListSerializer
    module = "articles"
    permission_classes = [HasPermission("articles.view")]

    def get_queryset(self):
        qs = self.filtered().select_related("category", "author")
        if category := self.request.query_params.get("category"):
            qs = qs.filter(category_id=category)
        return qs


class ArticleDetailView(_BaseContentDetail):
    model = Article
    write_serializer = ArticleWriteSerializer
    detail_serializer = ArticleDetailSerializer
    module = "articles"
    permission_classes = [HasPermission("articles.view")]


class ArticlePublishView(_BasePublishView):
    model = Article
    detail_serializer = ArticleDetailSerializer
    module = "articles"
    permission_classes = [HasPermission("articles.view")]


# ─── Events ───

class EventListCreateView(_BaseContentList):
    model = Event
    write_serializer = EventWriteSerializer
    detail_serializer = EventSerializer
    serializer_class = EventSerializer
    module = "events"
    permission_classes = [HasPermission("events.view")]

    def get_queryset(self):
        return self.filtered()


class EventDetailView(_BaseContentDetail):
    model = Event
    write_serializer = EventWriteSerializer
    detail_serializer = EventSerializer
    module = "events"
    permission_classes = [HasPermission("events.view")]


class EventPublishView(_BasePublishView):
    model = Event
    detail_serializer = EventSerializer
    module = "events"
    permission_classes = [HasPermission("events.view")]


# ─── News (reuses the publishable lifecycle) ───

from .models import FAQ, News, Page, SiteSetting  # noqa: E402
from .serializers import (  # noqa: E402
    FAQSerializer,
    NewsDetailSerializer,
    NewsListSerializer,
    NewsWriteSerializer,
    PageSerializer,
    PageWriteSerializer,
)


class NewsListCreateView(_BaseContentList):
    model = News
    write_serializer = NewsWriteSerializer
    detail_serializer = NewsDetailSerializer
    serializer_class = NewsListSerializer
    module = "news"
    permission_classes = [HasPermission("news.view")]

    def get_queryset(self):
        return self.filtered()


class NewsDetailView(_BaseContentDetail):
    model = News
    write_serializer = NewsWriteSerializer
    detail_serializer = NewsDetailSerializer
    module = "news"
    permission_classes = [HasPermission("news.view")]


class NewsPublishView(_BasePublishView):
    model = News
    detail_serializer = NewsDetailSerializer
    module = "news"
    permission_classes = [HasPermission("news.view")]


# ─── Pages ───

class PageListCreateView(_BaseContentList):
    model = Page
    write_serializer = PageWriteSerializer
    detail_serializer = PageSerializer
    serializer_class = PageSerializer
    module = "pages"
    permission_classes = [HasPermission("pages.view")]

    def get_queryset(self):
        return Page.objects.all().order_by("slug")


class PageDetailView(_BaseContentDetail):
    model = Page
    write_serializer = PageWriteSerializer
    detail_serializer = PageSerializer
    module = "pages"
    permission_classes = [HasPermission("pages.view")]


class PagePublishView(_BasePublishView):
    model = Page
    detail_serializer = PageSerializer
    module = "pages"
    permission_classes = [HasPermission("pages.view")]


# ─── FAQs ───

class FAQListCreateView(APIView):
    permission_classes = [HasPermission("faqs.view")]

    def get(self, request):
        return Response({"faqs": FAQSerializer(FAQ.objects.all(), many=True).data})

    def post(self, request):
        if not HasPermission("faqs.create")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing faqs.create", status_code=403)
        serializer = FAQSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        last = FAQ.objects.order_by("-sort_order").first()
        faq = serializer.save(sort_order=(last.sort_order + 1) if last else 1)
        audit(request, "faq.created", module="faqs", target_type="faq",
              target_id=str(faq.id), target_label=faq.question_ar[:80])
        return Response(FAQSerializer(faq).data, status=status.HTTP_201_CREATED)


class FAQDetailView(APIView):
    permission_classes = [HasPermission("faqs.edit")]

    def _get_faq(self, faq_id):
        faq = FAQ.objects.filter(id=faq_id).first()
        if faq is None:
            raise _not_found("السؤال")
        return faq

    def patch(self, request, faq_id):
        faq = self._get_faq(faq_id)
        # is_published toggling is publishing (spec: faqs carries a publish action).
        if "is_published" in request.data and not HasPermission("faqs.publish")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية النشر", "Missing faqs.publish", status_code=403)
        serializer = FAQSerializer(faq, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(request, "faq.updated", module="faqs", target_type="faq",
              target_id=str(faq.id), target_label=faq.question_ar[:80])
        return Response(serializer.data)

    def delete(self, request, faq_id):
        if not HasPermission("faqs.delete")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing faqs.delete", status_code=403)
        faq = self._get_faq(faq_id)
        audit(request, "faq.deleted", module="faqs", target_type="faq",
              target_id=str(faq.id), target_label=faq.question_ar[:80])
        faq.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FAQReorderView(APIView):
    """PUT {ordered_ids: []} — persist a full ordering."""

    permission_classes = [HasPermission("faqs.edit")]

    def put(self, request):
        ordered_ids = request.data.get("ordered_ids", [])
        if not isinstance(ordered_ids, list):
            raise ApiError("invalid_payload", "حمولة غير صالحة", "ordered_ids must be a list", status_code=400)
        for position, faq_id in enumerate(ordered_ids, start=1):
            FAQ.objects.filter(id=faq_id).update(sort_order=position)
        audit(request, "faq.reordered", module="faqs")
        return Response({"faqs": FAQSerializer(FAQ.objects.all(), many=True).data})


# ─── Homepage settings ───

HOMEPAGE_KEY = "homepage"
HOMEPAGE_FIELDS = [
    "hero_title_ar", "hero_title_en",
    "hero_subtitle_ar", "hero_subtitle_en",
    "hero_eyebrow_ar", "hero_eyebrow_en",
]


class HomepageSettingsView(APIView):
    permission_classes = [HasPermission("homepage.view")]

    def get(self, request):
        setting = SiteSetting.objects.filter(key=HOMEPAGE_KEY).first()
        return Response({"homepage": setting.value if setting else {}})

    def put(self, request):
        if not HasPermission("homepage.edit")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing homepage.edit", status_code=403)
        value = {
            field: str(request.data.get(field, "") or "")[:300]
            for field in HOMEPAGE_FIELDS
        }
        setting, _ = SiteSetting.objects.get_or_create(key=HOMEPAGE_KEY)
        before = setting.value
        setting.value = value
        setting.save(update_fields=["value", "updated_at"])
        audit(request, "homepage.updated", module="homepage", before=before, after=value)
        return Response({"homepage": value})


# ─── Homepage collections: generic sortable/publishable CRUD ───

from .models import GalleryItem, Partner, Testimonial, Thesis  # noqa: E402
from .serializers import (  # noqa: E402
    GalleryItemSerializer,
    PartnerSerializer,
    TestimonialSerializer,
    ThesisSerializer,
)


def build_collection_views(model, serializer_cls, module, label_of):
    """List/Create + Detail(PATCH/DELETE) + Reorder for an ordered collection.

    view → <module>.view · create/delete/reorder → <module>.edit unless the
    module has its own create/delete actions (theses does; homepage doesn't).
    """
    from apps.rbac.models import Permission

    def perm_or_edit(action):
        exists = Permission.objects.filter(module__key=module, action=action).exists()
        return f"{module}.{action}" if exists else f"{module}.edit"

    verb = model.__name__.lower()

    class ListCreate(APIView):
        permission_classes = [HasPermission(f"{module}.view")]

        def get(self, request):
            return Response({"items": serializer_cls(model.objects.all(), many=True).data})

        def post(self, request):
            if not HasPermission(perm_or_edit("create"))().has_permission(request, self):
                raise ApiError("forbidden", "ليست لديك صلاحية", "Missing permission", status_code=403)
            serializer = serializer_cls(data=request.data)
            serializer.is_valid(raise_exception=True)
            last = model.objects.order_by("-sort_order").first()
            obj = serializer.save(sort_order=(last.sort_order + 1) if last else 1)
            audit(request, f"{verb}.created", module=module,
                  target_type=verb, target_id=str(obj.id), target_label=label_of(obj))
            return Response(serializer_cls(obj).data, status=status.HTTP_201_CREATED)

    class Detail(APIView):
        permission_classes = [HasPermission(f"{module}.edit")]

        def patch(self, request, object_id):
            obj = model.objects.filter(id=object_id).first()
            if obj is None:
                raise _not_found()
            if "is_published" in request.data and not HasPermission(perm_or_edit("publish"))().has_permission(request, self):
                raise ApiError("forbidden", "ليست لديك صلاحية النشر", "Missing publish permission", status_code=403)
            serializer = serializer_cls(obj, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            audit(request, f"{verb}.updated", module=module,
                  target_type=verb, target_id=str(obj.id), target_label=label_of(obj))
            return Response(serializer.data)

        def delete(self, request, object_id):
            if not HasPermission(perm_or_edit("delete"))().has_permission(request, self):
                raise ApiError("forbidden", "ليست لديك صلاحية", "Missing permission", status_code=403)
            obj = model.objects.filter(id=object_id).first()
            if obj is None:
                raise _not_found()
            audit(request, f"{verb}.deleted", module=module,
                  target_type=verb, target_id=str(obj.id), target_label=label_of(obj))
            obj.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    class Reorder(APIView):
        permission_classes = [HasPermission(f"{module}.edit")]

        def put(self, request):
            ordered_ids = request.data.get("ordered_ids", [])
            if not isinstance(ordered_ids, list):
                raise ApiError("invalid_payload", "حمولة غير صالحة", "ordered_ids must be a list", status_code=400)
            for position, object_id in enumerate(ordered_ids, start=1):
                model.objects.filter(id=object_id).update(sort_order=position)
            audit(request, f"{verb}.reordered", module=module)
            return Response({"items": serializer_cls(model.objects.all(), many=True).data})

    return ListCreate, Detail, Reorder


TestimonialListCreateView, TestimonialDetailView, TestimonialReorderView = build_collection_views(
    Testimonial, TestimonialSerializer, "homepage", lambda o: o.name_ar)
PartnerListCreateView, PartnerDetailView, PartnerReorderView = build_collection_views(
    Partner, PartnerSerializer, "homepage", lambda o: o.name_ar)
GalleryListCreateView, GalleryDetailView, GalleryReorderView = build_collection_views(
    GalleryItem, GalleryItemSerializer, "homepage", lambda o: o.media.original_name)
ThesisListCreateView, ThesisDetailView, ThesisReorderView = build_collection_views(
    Thesis, ThesisSerializer, "theses", lambda o: o.title_ar[:80])


# ─── Nested homepage settings schema (replaces the flat hero-only form) ───

HOMEPAGE_TEXT_SCHEMA = {
    "hero": ["eyebrow_ar", "eyebrow_en", "title_ar", "title_en", "subtitle_ar", "subtitle_en",
             "patron_prefix_ar", "patron_prefix_en", "patron_ar", "patron_en",
             "cta_primary_ar", "cta_primary_en", "cta_secondary_ar", "cta_secondary_en"],
    "vision": ["label_ar", "label_en", "subtitle_ar", "subtitle_en",
               "card_title_ar", "card_title_en", "body_ar", "body_en",
               "image_1", "image_2"],
    "sections": ["programs_label_ar", "programs_label_en", "programs_subtitle_ar", "programs_subtitle_en",
                 "theses_label_ar", "theses_label_en", "theses_subtitle_ar", "theses_subtitle_en",
                 "features_label_ar", "features_label_en", "features_subtitle_ar", "features_subtitle_en",
                 "testimonials_label_ar", "testimonials_label_en", "testimonials_subtitle_ar", "testimonials_subtitle_en",
                 "gallery_label_ar", "gallery_label_en", "gallery_subtitle_ar", "gallery_subtitle_en",
                 "partners_label_ar", "partners_label_en",
                 "apply_label_ar", "apply_label_en", "apply_subtitle_ar", "apply_subtitle_en",
                 "apply_intro_ar", "apply_intro_en"],
}
MAX_STATS = 6
MAX_FEATURES = 6


def _clean_homepage(payload):
    if not isinstance(payload, dict):
        raise ApiError("invalid_payload", "حمولة غير صالحة", "Body must be an object", status_code=400)
    cleaned = {}
    for section, keys in HOMEPAGE_TEXT_SCHEMA.items():
        source = payload.get(section) or {}
        if not isinstance(source, dict):
            source = {}
        cleaned[section] = {k: str(source.get(k, "") or "")[:2000] for k in keys}
    def to_int(raw):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    stats = payload.get("stats") or []
    cleaned["stats"] = [
        {
            "value": to_int(s.get("value")),
            "label_ar": str(s.get("label_ar", "") or "")[:100],
            "label_en": str(s.get("label_en", "") or "")[:100],
        }
        for s in stats[:MAX_STATS] if isinstance(s, dict)
    ]
    features = payload.get("features") or []
    cleaned["features"] = [
        {
            "title_ar": str(f.get("title_ar", "") or "")[:150],
            "title_en": str(f.get("title_en", "") or "")[:150],
            "summary_ar": str(f.get("summary_ar", "") or "")[:200],
            "summary_en": str(f.get("summary_en", "") or "")[:200],
            "body_ar": str(f.get("body_ar", "") or "")[:1000],
            "body_en": str(f.get("body_en", "") or "")[:1000],
        }
        for f in features[:MAX_FEATURES] if isinstance(f, dict)
    ]
    return cleaned


class HomepageSettingsV2View(APIView):
    permission_classes = [HasPermission("homepage.view")]

    def get(self, request):
        setting = SiteSetting.objects.filter(key=HOMEPAGE_KEY).first()
        value = setting.value if setting else {}
        # Old flat-schema values are ignored gracefully.
        if value and "hero" not in value:
            value = {}
        return Response({"homepage": value})

    def put(self, request):
        if not HasPermission("homepage.edit")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing homepage.edit", status_code=403)
        value = _clean_homepage(request.data)
        setting, _ = SiteSetting.objects.get_or_create(key=HOMEPAGE_KEY)
        setting.value = value
        setting.save(update_fields=["value", "updated_at"])
        audit(request, "homepage.updated", module="homepage")
        return Response({"homepage": value})
