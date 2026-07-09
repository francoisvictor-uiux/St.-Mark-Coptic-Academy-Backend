"""OTP issue/verify (spec Part 4 §5.5): hashed, single-use, purpose-bound,
constant-time compared, rate-limited per identity."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.common.errors import ApiError

from .models import OTPCode, OTPPurpose

OTP_LENGTH = 6
OTP_TTL = {
    OTPPurpose.EMAIL_VERIFY: timedelta(minutes=15),
    OTPPurpose.PASSWORD_RESET: timedelta(minutes=10),
}
SEND_LIMIT_PER_HOUR = 5


def _hash_code(code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def issue_otp(user, purpose: str, sent_to: str) -> str:
    """Create a fresh code, invalidating prior unconsumed codes of the same purpose.

    Returns the plaintext code (for the email); only its HMAC is stored.
    """
    window_start = timezone.now() - timedelta(hours=1)
    recent = OTPCode.objects.filter(
        user=user, purpose=purpose, created_at__gte=window_start
    ).count()
    if recent >= SEND_LIMIT_PER_HOUR:
        raise ApiError(
            "otp_rate_limited",
            "طلبت رموزاً كثيرة — انتظر قليلاً ثم حاول مجدداً",
            "Too many codes requested — wait a while and try again",
            status_code=429,
            headers={"Retry-After": "3600"},
        )

    OTPCode.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True).update(
        consumed_at=timezone.now()
    )
    code = f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"
    OTPCode.objects.create(
        user=user,
        purpose=purpose,
        code_hash=_hash_code(code),
        sent_to=sent_to,
        expires_at=timezone.now() + OTP_TTL.get(purpose, timedelta(minutes=10)),
    )
    return code


def _invalid_code_error():
    return ApiError(
        "invalid_code",
        "الرمز غير صحيح أو منتهي الصلاحية",
        "The code is incorrect or has expired",
        status_code=400,
    )


INVITE_SALT = "smca.admin-invite"
INVITE_MAX_AGE = 72 * 3600  # 72h (spec ADM-02)


def issue_invite_token(user) -> str:
    """Signed 72h invite link token; single-use + revocable via a hashed OTP row."""
    from django.core import signing

    # Nonce keeps every token unique — two invites in the same second must
    # not produce the same signature, or revocation can't tell them apart.
    token = signing.dumps({"uid": str(user.id), "n": secrets.token_hex(4)}, salt=INVITE_SALT)
    OTPCode.objects.filter(
        user=user, purpose=OTPPurpose.INVITE, consumed_at__isnull=True
    ).update(consumed_at=timezone.now())
    OTPCode.objects.create(
        user=user,
        purpose=OTPPurpose.INVITE,
        code_hash=_hash_code(token),
        sent_to=user.email,
        expires_at=timezone.now() + timedelta(seconds=INVITE_MAX_AGE),
        max_attempts=10,
    )
    return token


def _invalid_invite_error():
    return ApiError(
        "invalid_invite",
        "رابط الدعوة غير صالح أو منتهي الصلاحية",
        "The invitation link is invalid or has expired",
        status_code=410,
    )


def verify_invite_token(token: str):
    """Resolve + consume an invite token. Returns the invited user or raises."""
    from django.core import signing

    from .models import User, UserStatus

    try:
        payload = signing.loads(token, salt=INVITE_SALT, max_age=INVITE_MAX_AGE)
    except signing.BadSignature:
        raise _invalid_invite_error()
    user = User.objects.filter(
        id=payload["uid"], status=UserStatus.INVITED, deleted_at__isnull=True
    ).first()
    if user is None:
        raise _invalid_invite_error()
    otp = (
        OTPCode.objects.filter(user=user, purpose=OTPPurpose.INVITE, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if otp is None or otp.expires_at <= timezone.now() or not hmac.compare_digest(
        otp.code_hash, _hash_code(token)
    ):
        raise _invalid_invite_error()
    otp.consumed_at = timezone.now()
    otp.save(update_fields=["consumed_at", "updated_at"])
    return user


def revoke_invite(user) -> int:
    """Invalidate all outstanding invite tokens for the user."""
    return OTPCode.objects.filter(
        user=user, purpose=OTPPurpose.INVITE, consumed_at__isnull=True
    ).update(consumed_at=timezone.now())


def verify_otp(user, purpose: str, code: str) -> OTPCode:
    """Validate and consume the active code. Raises ApiError on any failure."""
    otp = (
        OTPCode.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if otp is None or otp.expires_at <= timezone.now():
        raise _invalid_code_error()
    if otp.attempts >= otp.max_attempts:
        raise ApiError(
            "too_many_attempts",
            "محاولات كثيرة خاطئة — اطلب رمزاً جديداً",
            "Too many wrong attempts — request a new code",
            status_code=400,
        )
    if not hmac.compare_digest(otp.code_hash, _hash_code(code)):
        otp.attempts += 1
        otp.save(update_fields=["attempts", "updated_at"])
        raise _invalid_code_error()
    otp.consumed_at = timezone.now()
    otp.save(update_fields=["consumed_at", "updated_at"])
    return otp
