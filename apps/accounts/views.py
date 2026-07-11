from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password as check_hash
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.errors import ApiError
from apps.students.models import StudentProfile

from .emails import send_templated
from .models import (
    LoginHistory,
    LoginResult,
    OTPPurpose,
    PasswordHistory,
    User,
    UserStatus,
)
from .serializers import (
    EmailSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResendOTPSerializer,
    ResetPasswordSerializer,
    UserSerializer,
    VerifyCodeSerializer,
)
from .services import OTP_TTL, issue_otp, verify_activation_token, verify_invite_token, verify_otp

RESET_TOKEN_SALT = "smca.password-reset"
RESET_TOKEN_MAX_AGE = 15 * 60  # seconds


def _require_csrf_header(request):
    """Cookie-authenticated endpoints require X-Requested-With (spec Part 4 §3)."""
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        raise ApiError(
            "missing_csrf_header",
            "الطلب مرفوض",
            "Request rejected: X-Requested-With header required",
            status_code=status.HTTP_403_FORBIDDEN,
        )


def _client_meta(request):
    return {
        "ip": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:1000],
    }


def _error(code, message_ar, message_en, http_status):
    return Response(
        {"error": {"code": code, "message_ar": message_ar, "message_en": message_en}},
        status=http_status,
    )


def _set_refresh_cookie(response, refresh_token, max_age_seconds):
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        str(refresh_token),
        max_age=max_age_seconds,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path=settings.REFRESH_COOKIE_PATH,
    )


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip().lower()
        password = serializer.validated_data["password"]
        remember_me = serializer.validated_data["remember_me"]
        meta = _client_meta(request)

        user = authenticate(request=request, username=identifier, password=password)

        if user is None:
            # Distinguish non-active statuses for correct-password owners only —
            # response text never reveals whether the email exists (spec Part 0 §4.8).
            existing = User.objects.filter(email=identifier, deleted_at__isnull=True).first()
            if existing and existing.check_password(password):
                if existing.status == UserStatus.PENDING_VERIFICATION:
                    LoginHistory.objects.create(
                        user=existing, identifier_entered=identifier,
                        result=LoginResult.UNVERIFIED, **meta,
                    )
                    return _error(
                        "unverified",
                        "حسابك بحاجة إلى تفعيل — تحقق من بريدك الإلكتروني",
                        "Your account needs verification — check your email",
                        status.HTTP_403_FORBIDDEN,
                    )
                if existing.status == UserStatus.PENDING_APPROVAL:
                    LoginHistory.objects.create(
                        user=existing, identifier_entered=identifier,
                        result=LoginResult.UNVERIFIED, **meta,
                    )
                    return _error(
                        "pending_approval",
                        "حسابك قيد مراجعة إدارة الأكاديمية. ستصلك رسالة تفعيل بعد الموافقة عليه",
                        "Your account is awaiting the Academy's approval — you'll get an activation email once it's approved",
                        status.HTTP_403_FORBIDDEN,
                    )
                if existing.status == UserStatus.SUSPENDED:
                    LoginHistory.objects.create(
                        user=existing, identifier_entered=identifier,
                        result=LoginResult.SUSPENDED, **meta,
                    )
                    return _error(
                        "suspended",
                        "تم تعليق هذا الحساب. تواصل مع إدارة الأكاديمية",
                        "This account is suspended. Please contact the Academy office",
                        status.HTTP_403_FORBIDDEN,
                    )
                if existing.status == UserStatus.INVITED:
                    return _error(
                        "invited",
                        "استخدم رابط الدعوة المرسل إلى بريدك لتعيين كلمة المرور",
                        "Use the invitation link sent to your email to set your password",
                        status.HTTP_403_FORBIDDEN,
                    )
            LoginHistory.objects.create(
                user=existing, identifier_entered=identifier,
                result=LoginResult.BAD_CREDENTIALS, **meta,
            )
            return _error(
                "invalid_credentials",
                "البريد الإلكتروني أو كلمة المرور غير صحيحة",
                "Incorrect email or password",
                status.HTTP_401_UNAUTHORIZED,
            )

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        LoginHistory.objects.create(
            user=user, identifier_entered=identifier, result=LoginResult.SUCCESS, **meta
        )

        refresh = RefreshToken.for_user(user)
        lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        if remember_me:
            lifetime = settings.REMEMBER_ME_REFRESH_LIFETIME
            refresh.set_exp(lifetime=lifetime)

        response = Response(
            {"access": str(refresh.access_token), "user": UserSerializer(user).data}
        )
        _set_refresh_cookie(response, refresh, int(lifetime.total_seconds()))
        return response


class RefreshView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        _require_csrf_header(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            return _error(
                "no_refresh_token",
                "انتهت الجلسة لحمايتك — سجّل الدخول للمتابعة",
                "Your session ended to keep you safe — sign in to continue",
                status.HTTP_401_UNAUTHORIZED,
            )
        serializer = TokenRefreshSerializer(data={"refresh": raw})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            return _error(
                "invalid_refresh_token",
                "انتهت الجلسة لحمايتك — سجّل الدخول للمتابعة",
                "Your session ended to keep you safe — sign in to continue",
                status.HTTP_401_UNAUTHORIZED,
            )
        data = serializer.validated_data
        response = Response({"access": data["access"]})
        # Rotation is on, so a new refresh token replaces the cookie.
        if data.get("refresh"):
            max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
            _set_refresh_cookie(response, data["refresh"], max_age)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        _require_csrf_header(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH)
        return response


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


def _login_payload(user, remember_me=False):
    """Access token + user body, refresh token in an httpOnly cookie."""
    refresh = RefreshToken.for_user(user)
    lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    if remember_me:
        lifetime = settings.REMEMBER_ME_REFRESH_LIFETIME
        refresh.set_exp(lifetime=lifetime)
    response = Response({"access": str(refresh.access_token), "user": UserSerializer(user).data})
    _set_refresh_cookie(response, refresh, int(lifetime.total_seconds()))
    return response


def _send_verify_email(user):
    code = issue_otp(user, OTPPurpose.EMAIL_VERIFY, user.email)
    send_templated(
        user.email,
        "verify_email",
        {
            "first_name": user.first_name_ar,
            "code": code,
            "ttl_minutes": int(OTP_TTL[OTPPurpose.EMAIL_VERIFY].total_seconds() // 60),
        },
    )


class CheckEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "check_email"

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        taken = User.objects.filter(
            email=serializer.validated_data["email"], deleted_at__isnull=True
        ).exists()
        return Response({"available": not taken})


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(email=data["email"], deleted_at__isnull=True).exists():
            raise ApiError(
                "email_taken",
                "هذا البريد الإلكتروني مسجل بالفعل",
                "This email is already registered",
                status_code=status.HTTP_409_CONFLICT,
                fields={"email": ["taken"]},
            )

        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=data["password"],
                first_name_ar=data["first_name_ar"],
                last_name_ar=data["last_name_ar"],
                full_name_en=data["full_name_en"],
                phone=data.get("phone") or "",
                locale=data["locale"],
                status=UserStatus.PENDING_APPROVAL,
                terms_version=settings.TERMS_VERSION,
                terms_accepted_at=timezone.now(),
            )
            PasswordHistory.objects.create(user=user, password_hash=user.password)
            StudentProfile.objects.create(
                user=user,
                country_code=(data.get("country_code") or "").upper(),
                diocese=data.get("diocese"),
                church=data.get("church"),
                church_other_text=data.get("church_other_text") or "",
                program_interest=data.get("program_interest"),
            )
        # Admin-approval flow: no OTP. Tell the user their account is pending
        # review; the activation link is emailed once an admin approves.
        send_templated(
            user.email,
            "registration_received",
            {"first_name": user.first_name_ar},
        )
        return Response(
            {"user_id": str(user.id), "status": "pending_approval"},
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_verify"

    def post(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.filter(email=data["email"], deleted_at__isnull=True).first()
        if user is None or user.status != UserStatus.PENDING_VERIFICATION:
            raise ApiError(
                "invalid_code",
                "الرمز غير صحيح أو منتهي الصلاحية",
                "The code is incorrect or has expired",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        verify_otp(user, OTPPurpose.EMAIL_VERIFY, data["code"])
        user.status = UserStatus.ACTIVE
        user.email_verified_at = timezone.now()
        user.save(update_fields=["status", "email_verified_at", "updated_at"])
        send_templated(
            user.email,
            "welcome",
            {"first_name": user.first_name_ar, "login_url": settings.FRONTEND_LOGIN_URL},
        )
        # Verified users go straight to their dashboard — no second login step.
        return _login_payload(user)


class ActivateAccountView(APIView):
    """POST /auth/activate {token} — the user clicks the emailed activation link
    after an admin approves their registration. Activates the account and logs
    them straight in."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        if not token:
            raise ApiError(
                "invalid_activation",
                "رابط التفعيل غير صالح أو منتهي الصلاحية",
                "The activation link is invalid or has expired",
                status_code=status.HTTP_410_GONE,
            )
        user = verify_activation_token(token)
        user.status = UserStatus.ACTIVE
        user.email_verified_at = timezone.now()
        user.save(update_fields=["status", "email_verified_at", "updated_at"])
        send_templated(
            user.email,
            "welcome",
            {"first_name": user.first_name_ar, "login_url": settings.FRONTEND_LOGIN_URL},
        )
        # Activated users go straight to their dashboard — no separate login step.
        return _login_payload(user)


class ResendOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_send"

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.filter(email=data["email"], deleted_at__isnull=True).first()
        # Response never reveals whether the email exists.
        if user is not None:
            if (
                data["purpose"] == OTPPurpose.EMAIL_VERIFY
                and user.status == UserStatus.PENDING_VERIFICATION
            ):
                _send_verify_email(user)
            elif data["purpose"] == OTPPurpose.PASSWORD_RESET:
                _send_reset_email(user)
        return Response({"sent": True})


def _send_reset_email(user):
    code = issue_otp(user, OTPPurpose.PASSWORD_RESET, user.email)
    send_templated(
        user.email,
        "reset_code",
        {
            "first_name": user.first_name_ar,
            "code": code,
            "ttl_minutes": int(OTP_TTL[OTPPurpose.PASSWORD_RESET].total_seconds() // 60),
        },
    )


class AcceptInviteView(APIView):
    """POST /auth/accept-invite {token, password} — invited admin sets a password
    and becomes active (spec ADM-02 §11, journey §3.2)."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ResetPasswordSerializer(
            data={"reset_token": request.data.get("token", ""), "password": request.data.get("password", "")}
        )
        serializer.is_valid(raise_exception=True)
        user = verify_invite_token(serializer.validated_data["reset_token"])
        with transaction.atomic():
            user.set_password(serializer.validated_data["password"])
            user.status = UserStatus.ACTIVE
            user.email_verified_at = timezone.now()
            user.save(update_fields=["password", "status", "email_verified_at", "updated_at"])
            PasswordHistory.objects.create(user=user, password_hash=user.password)
        from apps.audit.services import audit

        audit(request, "auth.invite_accepted", module="users", target=user)
        send_templated(
            user.email, "welcome",
            {"first_name": user.first_name_ar, "login_url": settings.FRONTEND_LOGIN_URL},
        )
        return _login_payload(user)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_send"

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email=serializer.validated_data["email"], deleted_at__isnull=True
        ).first()
        if user is not None and user.status in (UserStatus.ACTIVE, UserStatus.SUSPENDED):
            _send_reset_email(user)
        # Always 200 — never reveals whether the email exists.
        return Response({"sent": True})


class VerifyResetCodeView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_verify"

    def post(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.filter(email=data["email"], deleted_at__isnull=True).first()
        if user is None:
            raise ApiError(
                "invalid_code",
                "الرمز غير صحيح أو منتهي الصلاحية",
                "The code is incorrect or has expired",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        verify_otp(user, OTPPurpose.PASSWORD_RESET, data["code"])
        reset_token = signing.dumps({"uid": str(user.id)}, salt=RESET_TOKEN_SALT)
        return Response({"reset_token": reset_token})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            payload = signing.loads(
                data["reset_token"], salt=RESET_TOKEN_SALT, max_age=RESET_TOKEN_MAX_AGE
            )
        except signing.BadSignature:
            raise ApiError(
                "invalid_reset_token",
                "انتهت صلاحية رابط الاستعادة — ابدأ من جديد",
                "The reset link has expired — start over",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        user = User.objects.filter(id=payload["uid"], deleted_at__isnull=True).first()
        if user is None:
            raise ApiError(
                "invalid_reset_token",
                "انتهت صلاحية رابط الاستعادة — ابدأ من جديد",
                "The reset link has expired — start over",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Last-3 password reuse check (spec Part 4 §2 password_history).
        recent_hashes = [user.password] + list(
            user.password_history.order_by("-created_at").values_list(
                "password_hash", flat=True
            )[:3]
        )
        if any(check_hash(data["password"], h) for h in recent_hashes if h):
            raise ApiError(
                "password_reused",
                "لا يمكن استخدام كلمة مرور سبق استخدامها مؤخراً",
                "You cannot reuse a recent password",
                status_code=status.HTTP_400_BAD_REQUEST,
                fields={"password": ["reused"]},
            )

        with transaction.atomic():
            user.set_password(data["password"])
            user.save(update_fields=["password", "updated_at"])
            PasswordHistory.objects.create(user=user, password_hash=user.password)
        # Sign out every device: blacklist all outstanding refresh tokens.
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        send_templated(user.email, "password_changed", {"first_name": user.first_name_ar})
        return Response({"changed": True})
