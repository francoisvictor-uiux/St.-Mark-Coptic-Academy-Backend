from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.academics.models import Church, Diocese, Program
from apps.rbac.services import get_effective_permissions

from .models import OTPPurpose, User


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(trim_whitespace=False)
    remember_me = serializers.BooleanField(default=False)


class PasswordField(serializers.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("trim_whitespace", False)
        kwargs.setdefault("write_only", True)
        super().__init__(**kwargs)


def _run_password_validators(password, user=None):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = PasswordField()
    first_name_ar = serializers.CharField(max_length=50)
    last_name_ar = serializers.CharField(max_length=50)
    full_name_en = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    locale = serializers.ChoiceField(choices=["ar", "en"], default="ar")
    terms_accepted = serializers.BooleanField()
    # Step-2 academic identity (spec AUTH-02 §13 — register payload = step1+step2)
    country_code = serializers.CharField(
        max_length=2, required=False, allow_blank=True, default=""
    )
    diocese_id = serializers.PrimaryKeyRelatedField(
        source="diocese",
        queryset=Diocese.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        default=None,
    )
    church_id = serializers.PrimaryKeyRelatedField(
        source="church",
        queryset=Church.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        default=None,
    )
    church_other_text = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    program_interest_id = serializers.PrimaryKeyRelatedField(
        source="program_interest",
        queryset=Program.objects.filter(is_published=True),
        required=False,
        allow_null=True,
        default=None,
    )

    def validate_email(self, value):
        return value.strip().lower()

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError("Terms must be accepted")
        return value

    def validate(self, attrs):
        stub = User(
            email=attrs["email"],
            first_name_ar=attrs["first_name_ar"],
            last_name_ar=attrs["last_name_ar"],
            full_name_en=attrs["full_name_en"],
        )
        try:
            _run_password_validators(attrs["password"], user=stub)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"password": exc.detail})
        return attrs


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return value.strip().lower()


class VerifyCodeSerializer(EmailSerializer):
    code = serializers.RegexField(r"^\d{6}$")


class ResendOTPSerializer(EmailSerializer):
    purpose = serializers.ChoiceField(
        choices=[OTPPurpose.EMAIL_VERIFY, OTPPurpose.PASSWORD_RESET],
        default=OTPPurpose.EMAIL_VERIFY,
    )


class ResetPasswordSerializer(serializers.Serializer):
    reset_token = serializers.CharField(max_length=512)
    password = PasswordField()

    def validate_password(self, value):
        _run_password_validators(value)
        return value


class UserSerializer(serializers.ModelSerializer):
    name_ar = serializers.CharField(source="display_name_ar", read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "user_type",
            "first_name_ar",
            "last_name_ar",
            "name_ar",
            "full_name_en",
            "locale",
            "permissions",
        ]

    def get_permissions(self, user) -> list[str]:
        return get_effective_permissions(user)
