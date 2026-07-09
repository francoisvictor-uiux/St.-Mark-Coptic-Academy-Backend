"""Student self-service profile APIs (spec AUTH-09, Part 4 §3 STUDENT)."""

from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserType
from apps.audit.services import audit
from apps.common.errors import ApiError
from apps.content.services import process_image

from .models import StudentDocument, StudentProfile
from .serializers import StudentProfileSerializer, StudentProfileUpdateSerializer
from .services import refresh_completion

MAX_DOCUMENTS = 5
MAX_DOC_BYTES = 10 * 1024 * 1024
PDF_MAGIC = b"%PDF"


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.user_type == UserType.STUDENT)


def _own_profile(request) -> StudentProfile:
    profile = StudentProfile.objects.select_related(
        "diocese", "church", "program_interest"
    ).filter(user=request.user).first()
    if profile is None:
        # Legacy accounts created before the profile stub existed.
        profile = StudentProfile.objects.create(user=request.user)
    return profile


class MyProfileView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        return Response(StudentProfileSerializer(_own_profile(request)).data)

    def patch(self, request):
        profile = _own_profile(request)
        serializer = StudentProfileUpdateSerializer(
            data=request.data, partial=True, context={"profile": profile}
        )
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(profile, field, value)
        profile.save()
        refresh_completion(profile)
        return Response(StudentProfileSerializer(profile).data)


class MyPhotoView(APIView):
    permission_classes = [IsStudent]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ApiError("missing_file", "أرفق صورة", "Attach an image", status_code=400)
        # Avatars re-encode down to 512px (spec AUTH-09 §5).
        content, _, _, _, _ = process_image(uploaded, max_dimension=512)
        profile = _own_profile(request)
        if profile.photo:
            profile.photo.delete(save=False)
        profile.photo = content
        profile.save(update_fields=["photo", "updated_at"])
        refresh_completion(profile)
        return Response(StudentProfileSerializer(profile).data)

    def delete(self, request):
        profile = _own_profile(request)
        if profile.photo:
            profile.photo.delete(save=False)
            profile.photo = None
            profile.save(update_fields=["photo", "updated_at"])
            refresh_completion(profile)
        return Response(StudentProfileSerializer(profile).data)


def _validate_document(uploaded):
    if uploaded.size > MAX_DOC_BYTES:
        raise ApiError(
            "file_too_large", "حجم الملف يتجاوز ١٠ ميجابايت",
            "File exceeds the 10MB limit", status_code=400,
        )
    head = uploaded.read(8)
    uploaded.seek(0)
    if head.startswith(PDF_MAGIC):
        return "application/pdf"
    try:
        from PIL import Image

        image = Image.open(uploaded)
        image.verify()
        uploaded.seek(0)
        if image.format in ("JPEG", "PNG"):
            return f"image/{image.format.lower()}"
    except Exception:
        pass
    raise ApiError(
        "invalid_document", "المسموح ملفات PDF أو صور JPG/PNG",
        "Only PDF or JPG/PNG files are allowed", status_code=400,
    )


class MyDocumentsView(APIView):
    permission_classes = [IsStudent]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ApiError("missing_file", "أرفق ملفًا", "Attach a file", status_code=400)
        active = StudentDocument.objects.filter(user=request.user, deleted_at__isnull=True).count()
        if active >= MAX_DOCUMENTS:
            raise ApiError(
                "document_quota", "الحد الأقصى ٥ مستندات — احذف مستندًا أولًا",
                "Maximum 5 documents — delete one first", status_code=400,
            )
        mime = _validate_document(uploaded)
        document = StudentDocument.objects.create(
            user=request.user,
            file=uploaded,
            original_name=uploaded.name[:255],
            mime=mime,
            size_bytes=uploaded.size,
        )
        audit(request, "student.document_uploaded", module="admissions", target=request.user,
              after={"name": document.original_name, "size": document.size_bytes})
        profile = _own_profile(request)
        return Response(StudentProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class MyDocumentDetailView(APIView):
    permission_classes = [IsStudent]

    def delete(self, request, document_id):
        document = StudentDocument.objects.filter(
            id=document_id, user=request.user, deleted_at__isnull=True
        ).first()
        if document is None:
            raise ApiError("not_found", "المستند غير موجود", "Document not found", status_code=404)
        document.deleted_at = timezone.now()
        document.save(update_fields=["deleted_at", "updated_at"])
        audit(request, "student.document_deleted", module="admissions", target=request.user,
              before={"name": document.original_name})
        return Response(status=status.HTTP_204_NO_CONTENT)
