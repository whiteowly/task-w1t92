from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from iam.models import AuthSession, LoginFailure, UserOrganizationRole


LOCKOUT_WINDOW = timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)


def _get_failure_row(username, organization):
    failure, _ = LoginFailure.objects.get_or_create(
        username=username, organization=organization
    )
    return failure


def assert_not_locked(username, organization):
    failure = _get_failure_row(username=username, organization=organization)
    if failure.is_locked():
        seconds_left = int((failure.locked_until - timezone.now()).total_seconds())
        return False, max(seconds_left, 1)
    return True, 0


@transaction.atomic
def register_login_failure(username, organization):
    failure = _get_failure_row(username=username, organization=organization)
    now = timezone.now()

    if failure.last_failed_at and now - failure.last_failed_at > LOCKOUT_WINDOW:
        failure.failed_attempts = 0

    failure.failed_attempts += 1
    failure.last_failed_at = now

    if failure.failed_attempts >= settings.LOGIN_LOCKOUT_THRESHOLD:
        failure.locked_until = now + LOCKOUT_WINDOW
        failure.failed_attempts = 0

    failure.save(
        update_fields=[
            "failed_attempts",
            "last_failed_at",
            "locked_until",
            "updated_at",
        ]
    )


def clear_login_failures(username, organization):
    LoginFailure.objects.filter(username=username, organization=organization).delete()


def authenticate_with_lockout(username, password, organization):
    can_login, wait_seconds = assert_not_locked(
        username=username, organization=organization
    )
    if not can_login:
        return None, "locked", wait_seconds

    user = authenticate(username=username, password=password)
    if user is None:
        register_login_failure(username=username, organization=organization)
        return None, "invalid_credentials", 0

    is_member = UserOrganizationRole.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
    ).exists()
    if not is_member:
        return None, "not_in_organization", 0

    clear_login_failures(username=username, organization=organization)
    return user, "ok", 0


def create_auth_session(
    *, user, organization, ip_address: str | None = None, user_agent: str = ""
) -> AuthSession:
    now = timezone.now()
    auth_session = AuthSession.objects.create(
        session_key=AuthSession.new_session_key(),
        user=user,
        organization=organization,
        last_activity_at=now,
        expires_at=AuthSession.expiry_from_now(),
        ip_address=ip_address,
        user_agent=user_agent[:512],
    )
    return auth_session


def touch_session(auth_session: AuthSession):
    now = timezone.now()
    if now - auth_session.last_activity_at < timedelta(minutes=1):
        return

    auth_session.last_activity_at = now
    auth_session.expires_at = now + timedelta(
        seconds=settings.SESSION_INACTIVITY_TIMEOUT_SECONDS
    )
    auth_session.save(update_fields=["last_activity_at", "expires_at", "updated_at"])


def revoke_session(auth_session: AuthSession, reason: str):
    if auth_session.revoked_at is not None:
        return
    auth_session.revoked_at = timezone.now()
    auth_session.revoked_reason = reason[:255]
    auth_session.save(update_fields=["revoked_at", "revoked_reason", "updated_at"])


def revoke_user_sessions(user, reason: str):
    now = timezone.now()
    AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=now,
        revoked_reason=reason[:255],
        updated_at=now,
    )
