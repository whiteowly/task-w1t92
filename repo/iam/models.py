import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from common.constants import RoleCode
from common.models import TimestampedModel
from iam.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "username"

    objects = UserManager()

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username


class Role(TimestampedModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class UserOrganizationRole(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_roles",
    )
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.CASCADE, related_name="user_roles"
    )
    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, related_name="user_assignments"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "organization", "role")
        indexes = [
            models.Index(fields=["organization", "user"]),
            models.Index(fields=["organization", "role"]),
        ]


class AuthSession(TimestampedModel):
    session_key = models.CharField(max_length=128, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_sessions"
    )
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.CASCADE, related_name="auth_sessions"
    )
    last_activity_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "user", "revoked_at"]),
            models.Index(fields=["expires_at"]),
        ]

    @classmethod
    def new_session_key(cls) -> str:
        return secrets.token_urlsafe(48)

    @classmethod
    def expiry_from_now(cls) -> timezone.datetime:
        timeout = timedelta(seconds=settings.SESSION_INACTIVITY_TIMEOUT_SECONDS)
        return timezone.now() + timeout

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()


class LoginFailure(TimestampedModel):
    username = models.CharField(max_length=150)
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="login_failures",
        null=True,
        blank=True,
    )
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("username", "organization")
        indexes = [
            models.Index(fields=["username", "organization"]),
            models.Index(fields=["locked_until"]),
        ]

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())


DEFAULT_ROLE_SEED = [
    (RoleCode.ADMINISTRATOR.value, "Administrator"),
    (RoleCode.CLUB_MANAGER.value, "Club Manager"),
    (RoleCode.COUNSELOR_REVIEWER.value, "Counselor/Reviewer"),
    (RoleCode.GROUP_LEADER.value, "Group Leader"),
    (RoleCode.MEMBER.value, "Member"),
]
