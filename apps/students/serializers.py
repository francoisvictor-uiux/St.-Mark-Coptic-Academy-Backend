"""Student self-service profile serializers (spec AUTH-09)."""

from datetime import date

from rest_framework import serializers

from .models import EducationLevel, Gender, StudentDocument, StudentProfile


class StudentDocumentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = StudentDocument
        fields = ["id", "url", "original_name", "mime", "size_bytes", "verified_at", "created_at"]

    def get_url(self, obj) -> str:
        return obj.file.url


class StudentProfileSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    diocese_name = serializers.SerializerMethodField()
    church_name = serializers.SerializerMethodField()
    program_name = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            "photo_url", "gender", "date_of_birth", "nationality_code",
            "education_level", "education_field", "church_service", "confession_father",
            "bio", "emergency_name", "emergency_relation", "emergency_phone",
            "completion_pct", "country_code", "church_other_text",
            "diocese_name", "church_name", "program_name", "documents",
        ]

    def get_photo_url(self, obj) -> str:
        return obj.photo.url if obj.photo else ""

    def get_diocese_name(self, obj) -> str:
        return obj.diocese.name_ar if obj.diocese else ""

    def get_church_name(self, obj) -> str:
        return obj.church.name_ar if obj.church else obj.church_other_text

    def get_program_name(self, obj) -> str:
        return obj.program_interest.name_ar if obj.program_interest else ""

    def get_documents(self, obj):
        docs = obj.user.documents.filter(deleted_at__isnull=True).order_by("-created_at")
        return StudentDocumentSerializer(docs, many=True).data


class StudentProfileUpdateSerializer(serializers.Serializer):
    """Per-section PATCH — every field optional (spec: sections save independently)."""

    gender = serializers.ChoiceField(choices=Gender.choices, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    nationality_code = serializers.CharField(max_length=2, required=False, allow_blank=True)
    education_level = serializers.ChoiceField(
        choices=EducationLevel.choices, required=False, allow_blank=True
    )
    education_field = serializers.CharField(max_length=120, required=False, allow_blank=True)
    church_service = serializers.CharField(max_length=120, required=False, allow_blank=True)
    confession_father = serializers.CharField(max_length=120, required=False, allow_blank=True)
    bio = serializers.CharField(max_length=500, required=False, allow_blank=True)
    emergency_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    emergency_relation = serializers.CharField(max_length=60, required=False, allow_blank=True)
    emergency_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_date_of_birth(self, value):
        if value is None:
            return value
        age = (date.today() - value).days / 365.25
        if age < 15 or age > 100:
            raise serializers.ValidationError("age must be between 15 and 100")
        return value

    def validate(self, attrs):
        # Emergency contact is all-or-none (spec AUTH-09 §6) — evaluated on the
        # final state, so partial PATCHes can't leave a half-filled contact.
        profile = self.context["profile"]
        final = {
            field: attrs.get(field, getattr(profile, field))
            for field in ("emergency_name", "emergency_relation", "emergency_phone")
        }
        filled = [bool(v) for v in final.values()]
        if any(filled) and not all(filled):
            raise serializers.ValidationError(
                {"emergency": ["all three emergency fields are required together"]}
            )
        return attrs
