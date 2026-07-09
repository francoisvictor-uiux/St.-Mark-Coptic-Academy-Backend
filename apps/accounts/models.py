import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base: UUID pk + created/updated timestamps (spec Part 4 §2)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserType(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super Admin"
    ADMIN = "admin", "Admin"
    STUDENT = "student", "Student"


class UserStatus(models.TextChoices):
    PENDING_VERIFICATION = "pending_verification", "Pending verification"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    INVITED = "invited", "Invited"
    # Reserved for the future manual-approval toggle (spec Part 0 §4.2).
    PENDING_APPROVAL = "pending_approval", "Pending approval"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("user_type", UserType.STUDENT)
        extra_fields.setdefault("status", UserStatus.PENDING_VERIFICATION)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields["user_type"] = UserType.SUPER_ADMIN
        extra_fields["status"] = UserStatus.ACTIVE
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        extra_fields.setdefault("email_verified_at", timezone.now())
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=60, unique=True, null=True, blank=True)
    first_name_ar = models.CharField(max_length=50)
    last_name_ar = models.CharField(max_length=50)
    full_name_en = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, default="")
    user_type = models.CharField(max_length=20, choices=UserType.choices, default=UserType.STUDENT)
    status = models.CharField(
        max_length=30, choices=UserStatus.choices, default=UserStatus.PENDING_VERIFICATION
    )
    locale = models.CharField(max_length=5, default="ar")
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=20, blank=True, default="")
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="invitees"
    )
    invitation_sent_at = models.DateTimeField(null=True, blank=True)
    account_expires_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_staff = models.BooleanField(default=False)  # Django admin (emergency access) only

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name_ar", "last_name_ar", "full_name_en"]

    class Meta:
        db_table = "users"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="uniq_users_email_ci"),
        ]
        indexes = [models.Index(fields=["user_type", "status"])]

    def __str__(self):
        return self.email

    @property
    def is_active(self):
        return self.status == UserStatus.ACTIVE and self.deleted_at is None

    @property
    def display_name_ar(self):
        return f"{self.first_name_ar} {self.last_name_ar}".strip()


class OTPPurpose(models.TextChoices):
    EMAIL_VERIFY = "email_verify", "Email verification"
    PHONE_VERIFY = "phone_verify", "Phone verification"
    PASSWORD_RESET = "password_reset", "Password reset"
    INVITE = "invite", "Admin invitation"
    TWO_FACTOR = "two_factor", "Two-factor challenge"


class OTPCode(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_codes")
    purpose = models.CharField(max_length=20, choices=OTPPurpose.choices)
    code_hash = models.CharField(max_length=128)
    sent_to = models.CharField(max_length=254)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "otp_codes"
        indexes = [models.Index(fields=["user", "purpose"])]


class LoginResult(models.TextChoices):
    SUCCESS = "success", "Success"
    BAD_CREDENTIALS = "bad_credentials", "Bad credentials"
    LOCKED = "locked", "Locked"
    SUSPENDED = "suspended", "Suspended"
    UNVERIFIED = "unverified", "Unverified"


class LoginHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_history"
    )
    identifier_entered = models.CharField(max_length=254)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    result = models.CharField(max_length=20, choices=LoginResult.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "login_history"
        indexes = [models.Index(fields=["created_at"])]


class PasswordHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_history")
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "password_history"


class EmailStatus(models.TextChoices):
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class EmailLog(models.Model):
    """One row per outgoing email attempt — the send audit trail.

    Never stores the body: OTP codes must not exist in plaintext at rest
    (spec Part 4 §5.5). Feeds the future admin "email failures" view.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    to_email = models.EmailField()
    template = models.CharField(max_length=50)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=EmailStatus.choices)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status", "template"]),
        ]

    def __str__(self):
        return f"{self.status}: {self.template} -> {self.to_email}"
