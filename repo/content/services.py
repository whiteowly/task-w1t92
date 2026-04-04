from __future__ import annotations

import csv
import hashlib
import io
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from django.db import transaction
from rest_framework import status

from common.exceptions import DomainAPIException
from content.models import (
    AssetState,
    ContentAsset,
    ContentAssetVersionLog,
    ContentArtifact,
    ContentDownloadRequestLog,
    ContentDownloadToken,
    ContentEntitlement,
    ContentRedeemCode,
    DownloadTokenPurpose,
    EntitlementSource,
)
from content.serializers import AssetImportItemSerializer
from content.storage_paths import normalize_storage_path, resolve_storage_path
from observability.services import log_audit_event

IMPORT_FIELDS = [
    "external_id",
    "title",
    "creator",
    "period",
    "style",
    "medium",
    "size",
    "source",
    "copyright_status",
    "tags",
    "state",
    "allow_download",
    "allow_share",
    "storage_path",
]


def _asset_snapshot(asset: ContentAsset) -> dict:
    return {
        "external_id": asset.external_id,
        "title": asset.title,
        "creator": asset.creator,
        "period": asset.period,
        "style": asset.style,
        "medium": asset.medium,
        "size": asset.size,
        "source": asset.source,
        "copyright_status": asset.copyright_status,
        "tags": list(asset.tags or []),
        "state": asset.state,
        "allow_download": asset.allow_download,
        "allow_share": asset.allow_share,
        "storage_path": asset.storage_path,
    }


def _validated_storage_path_or_error(storage_path: str) -> str:
    try:
        return normalize_storage_path(storage_path)
    except ValueError as exc:
        raise DomainAPIException(
            code="content.asset.storage_path_invalid",
            message=str(exc),
        ) from exc


def _append_version_log(*, asset: ContentAsset, actor, reason: str):
    ContentAssetVersionLog.objects.create(
        organization=asset.organization,
        asset=asset,
        version=asset.version,
        state=asset.state,
        changed_by=actor,
        change_reason=reason,
        snapshot=_asset_snapshot(asset),
    )


@transaction.atomic
def create_asset(*, organization, actor, payload: dict, request) -> ContentAsset:
    storage_path = _validated_storage_path_or_error(payload.get("storage_path", ""))
    asset = ContentAsset.objects.create(
        organization=organization,
        external_id=payload["external_id"],
        title=payload["title"],
        creator=payload.get("creator", ""),
        period=payload.get("period", ""),
        style=payload.get("style", ""),
        medium=payload.get("medium", ""),
        size=payload.get("size", ""),
        source=payload.get("source", ""),
        copyright_status=payload.get("copyright_status", ""),
        tags=payload.get("tags", []),
        state=AssetState.DRAFT,
        version=1,
        allow_download=payload.get("allow_download", False),
        allow_share=payload.get("allow_share", False),
        storage_path=storage_path,
    )
    _append_version_log(asset=asset, actor=actor, reason="asset_created")

    log_audit_event(
        action="content.asset.create",
        organization=organization,
        actor_user=actor,
        request=request,
        resource_type="content_asset",
        resource_id=str(asset.id),
        metadata={"external_id": asset.external_id, "version": asset.version},
    )
    return asset


@transaction.atomic
def update_asset(*, asset: ContentAsset, actor, payload: dict, request) -> ContentAsset:
    asset = ContentAsset.objects.select_for_update().get(pk=asset.pk)
    before_snapshot = _asset_snapshot(asset)

    mutable_payload = dict(payload)
    if "storage_path" in mutable_payload:
        mutable_payload["storage_path"] = _validated_storage_path_or_error(
            mutable_payload.get("storage_path", "")
        )

    for field in [
        "title",
        "creator",
        "period",
        "style",
        "medium",
        "size",
        "source",
        "copyright_status",
        "tags",
        "allow_download",
        "allow_share",
        "storage_path",
    ]:
        if field in mutable_payload:
            setattr(asset, field, mutable_payload[field])

    asset.version += 1
    asset.save()
    _append_version_log(asset=asset, actor=actor, reason="asset_updated")

    log_audit_event(
        action="content.asset.update",
        organization=asset.organization,
        actor_user=actor,
        request=request,
        resource_type="content_asset",
        resource_id=str(asset.id),
        metadata={"version": asset.version},
        before_data=before_snapshot,
        after_data=_asset_snapshot(asset),
    )
    return asset


@transaction.atomic
def set_asset_state(*, asset: ContentAsset, actor, to_state: str, request):
    asset = ContentAsset.objects.select_for_update().get(pk=asset.pk)
    if asset.state == to_state:
        raise DomainAPIException(
            code="content.asset.invalid_transition",
            message="Asset already in requested state.",
        )

    before_state = asset.state
    asset.state = to_state
    asset.version += 1
    asset.save(update_fields=["state", "version", "updated_at"])
    _append_version_log(asset=asset, actor=actor, reason=f"state_{to_state}")

    action = (
        "content.asset.publish"
        if to_state == AssetState.PUBLISHED
        else "content.asset.unpublish"
    )
    log_audit_event(
        action=action,
        organization=asset.organization,
        actor_user=actor,
        request=request,
        resource_type="content_asset",
        resource_id=str(asset.id),
        metadata={
            "from_state": before_state,
            "to_state": to_state,
            "version": asset.version,
        },
    )
    return asset


def _validate_import_items(*, organization, items: list[dict]):
    errors: list[dict] = []
    normalized_items: list[dict] = []
    seen_external_ids: set[str] = set()

    existing_external_ids = set(
        ContentAsset.objects.filter(
            organization=organization,
            external_id__in=[
                item.get("external_id") for item in items if item.get("external_id")
            ],
        ).values_list("external_id", flat=True)
    )

    for index, item in enumerate(items, start=1):
        serializer = AssetImportItemSerializer(data=item)
        if not serializer.is_valid():
            errors.append({"row": index, "errors": serializer.errors})
            continue

        validated = serializer.validated_data
        ext_id = validated["external_id"]
        if ext_id in seen_external_ids:
            errors.append(
                {
                    "row": index,
                    "errors": {
                        "external_id": ["Duplicate external_id within import payload."]
                    },
                }
            )
            continue
        seen_external_ids.add(ext_id)

        if ext_id in existing_external_ids:
            errors.append(
                {
                    "row": index,
                    "errors": {
                        "external_id": ["Duplicate external_id for this organization."]
                    },
                }
            )
            continue

        normalized_items.append(validated)

    if errors:
        raise DomainAPIException(
            code="content.import_validation_failed",
            message="Import validation failed.",
            details=errors,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return normalized_items


@transaction.atomic
def bulk_import_items(*, organization, actor, items: list[dict], request, source: str):
    normalized_items = _validate_import_items(organization=organization, items=items)

    created_assets = []
    for item in normalized_items:
        asset = ContentAsset.objects.create(
            organization=organization,
            external_id=item["external_id"],
            title=item["title"],
            creator=item.get("creator", ""),
            period=item.get("period", ""),
            style=item.get("style", ""),
            medium=item.get("medium", ""),
            size=item.get("size", ""),
            source=item.get("source", ""),
            copyright_status=item.get("copyright_status", ""),
            tags=item.get("tags", []),
            state=item.get("state", AssetState.DRAFT),
            version=1,
            allow_download=item.get("allow_download", False),
            allow_share=item.get("allow_share", False),
            storage_path=_validated_storage_path_or_error(item.get("storage_path", "")),
        )
        created_assets.append(asset)
        _append_version_log(asset=asset, actor=actor, reason=f"bulk_import_{source}")

    log_audit_event(
        action=f"content.asset.import.{source}",
        organization=organization,
        actor_user=actor,
        request=request,
        resource_type="content_asset",
        resource_id="bulk",
        metadata={"import_count": len(created_assets)},
    )
    return created_assets


def parse_csv_rows(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = reader.fieldnames or []
    if set(headers) != set(IMPORT_FIELDS):
        raise DomainAPIException(
            code="content.import_invalid_schema",
            message="CSV headers must exactly match required import schema.",
            details=[
                {
                    "field": "headers",
                    "code": "schema_mismatch",
                    "message": f"Expected headers: {', '.join(IMPORT_FIELDS)}",
                }
            ],
        )

    parsed_rows = []
    for row in reader:
        tags = [
            part.strip() for part in (row.get("tags") or "").split("|") if part.strip()
        ]
        parsed_rows.append(
            {
                "external_id": (row.get("external_id") or "").strip(),
                "title": (row.get("title") or "").strip(),
                "creator": (row.get("creator") or "").strip(),
                "period": (row.get("period") or "").strip(),
                "style": (row.get("style") or "").strip(),
                "medium": (row.get("medium") or "").strip(),
                "size": (row.get("size") or "").strip(),
                "source": (row.get("source") or "").strip(),
                "copyright_status": (row.get("copyright_status") or "").strip(),
                "tags": tags,
                "state": (row.get("state") or AssetState.DRAFT).strip()
                or AssetState.DRAFT,
                "allow_download": (row.get("allow_download") or "false").strip().lower()
                in {"1", "true", "yes"},
                "allow_share": (row.get("allow_share") or "false").strip().lower()
                in {"1", "true", "yes"},
                "storage_path": (row.get("storage_path") or "").strip(),
            }
        )
    return parsed_rows


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_manager_role(role_codes: set[str]) -> bool:
    return bool(role_codes.intersection({"administrator", "club_manager"}))


def user_has_asset_acl_access(
    *, user, role_codes: set[str], asset: ContentAsset
) -> bool:
    if _is_manager_role(role_codes):
        return True
    if asset.state != AssetState.PUBLISHED:
        return False

    user_id = str(user.id)
    return (
        asset.chapters.filter(
            acl_entries__can_view=True,
        )
        .filter(
            (
                Q(
                    acl_entries__principal_type="user",
                    acl_entries__principal_value=user_id,
                )
            )
            | (
                Q(acl_entries__principal_type="role")
                & Q(acl_entries__principal_value__in=list(role_codes))
            )
        )
        .exists()
    )


def user_has_entitlement(*, organization, user, asset: ContentAsset) -> bool:
    return ContentEntitlement.objects.filter(
        organization=organization,
        user=user,
        asset=asset,
        is_active=True,
    ).exists()


@transaction.atomic
def grant_subscription_entitlement(
    *, organization, user, asset: ContentAsset, actor, request
):
    entitlement, created = ContentEntitlement.objects.get_or_create(
        organization=organization,
        user=user,
        asset=asset,
        source=EntitlementSource.SUBSCRIPTION,
        defaults={
            "is_active": True,
            "granted_by": actor,
        },
    )
    if not created and not entitlement.is_active:
        entitlement.is_active = True
        entitlement.granted_by = actor
        entitlement.save(update_fields=["is_active", "granted_by", "updated_at"])

    log_audit_event(
        action="content.entitlement.subscription_grant",
        organization=organization,
        actor_user=actor,
        request=request,
        resource_type="content_entitlement",
        resource_id=str(entitlement.id),
        metadata={"asset_id": asset.id, "user_id": user.id},
    )
    return entitlement


@transaction.atomic
def create_redeem_code(
    *, organization, asset: ContentAsset, actor, request, expires_at=None
):
    expires_at = expires_at or (timezone.now() + timedelta(days=90))
    if expires_at <= timezone.now():
        raise DomainAPIException(
            code="content.redeem_code.invalid_expiry",
            message="Redeem code expiry must be in the future.",
        )

    code_plain = ""
    code_hash = ""
    for _ in range(10):
        candidate = "".join(
            secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(12)
        )
        candidate_hash = _sha256(candidate)
        exists = ContentRedeemCode.objects.filter(
            organization=organization,
            code_hash=candidate_hash,
        ).exists()
        if not exists:
            code_plain = candidate
            code_hash = candidate_hash
            break
    if not code_plain:
        raise DomainAPIException(
            code="content.redeem_code.generation_failed",
            message="Unable to generate unique redeem code.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = ContentRedeemCode.objects.create(
        organization=organization,
        asset=asset,
        code_hash=code_hash,
        code_last4=code_plain[-4:],
        expires_at=expires_at,
        created_by=actor,
    )

    log_audit_event(
        action="content.redeem_code.create",
        organization=organization,
        actor_user=actor,
        request=request,
        resource_type="content_redeem_code",
        resource_id=str(code.id),
        metadata={"asset_id": asset.id, "expires_at": expires_at.isoformat()},
    )
    return code, code_plain


@transaction.atomic
def redeem_code(*, organization, user, code_value: str, request):
    normalized_code = (code_value or "").strip().upper()
    if len(normalized_code) != 12:
        raise DomainAPIException(
            code="content.redeem_code.invalid_format",
            message="Redeem code must be exactly 12 characters.",
        )

    code_hash = _sha256(normalized_code)
    code = (
        ContentRedeemCode.objects.select_for_update()
        .filter(
            organization=organization,
            code_hash=code_hash,
        )
        .first()
    )

    if code is None:
        raise DomainAPIException(
            code="content.redeem_code.not_found",
            message="Redeem code is invalid.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if code.redeemed_at is not None:
        raise DomainAPIException(
            code="content.redeem_code.used",
            message="Redeem code has already been used.",
        )
    if code.expires_at <= timezone.now():
        raise DomainAPIException(
            code="content.redeem_code.expired",
            message="Redeem code has expired.",
        )

    code.redeemed_at = timezone.now()
    code.redeemed_by = user
    code.save(update_fields=["redeemed_at", "redeemed_by", "updated_at"])

    entitlement, _ = ContentEntitlement.objects.get_or_create(
        organization=organization,
        user=user,
        asset=code.asset,
        source=EntitlementSource.REDEEM_CODE,
        defaults={
            "is_active": True,
            "granted_by": user,
            "redeem_code_id": code.id,
        },
    )
    if not entitlement.is_active:
        entitlement.is_active = True
        entitlement.save(update_fields=["is_active", "updated_at"])

    log_audit_event(
        action="content.redeem_code.redeem",
        organization=organization,
        actor_user=user,
        request=request,
        resource_type="content_redeem_code",
        resource_id=str(code.id),
        metadata={"asset_id": code.asset_id, "entitlement_id": entitlement.id},
    )
    return entitlement


@transaction.atomic
def issue_download_token(
    *,
    organization,
    user,
    asset: ContentAsset,
    purpose: str,
    role_codes: set[str],
    request,
):
    if purpose == DownloadTokenPurpose.DOWNLOAD and not asset.allow_download:
        raise DomainAPIException(
            code="content.download.permission_denied",
            message="Download is disabled for this asset.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if purpose == DownloadTokenPurpose.SHARE and not asset.allow_share:
        raise DomainAPIException(
            code="content.share.permission_denied",
            message="Share is disabled for this asset.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not user_has_asset_acl_access(user=user, role_codes=role_codes, asset=asset):
        raise DomainAPIException(
            code="content.access.denied",
            message="Asset access denied by chapter ACL coverage.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not _is_manager_role(role_codes) and not user_has_entitlement(
        organization=organization,
        user=user,
        asset=asset,
    ):
        raise DomainAPIException(
            code="content.entitlement.required",
            message="No active entitlement for this content asset.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    token_plain = secrets.token_urlsafe(32)
    token = ContentDownloadToken.objects.create(
        organization=organization,
        user=user,
        asset=asset,
        token_hash=_sha256(token_plain),
        token_hint=token_plain[-8:],
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    log_audit_event(
        action="content.download_token.issue",
        organization=organization,
        actor_user=user,
        request=request,
        resource_type="content_download_token",
        resource_id=str(token.id),
        metadata={
            "asset_id": asset.id,
            "purpose": purpose,
            "expires_at": token.expires_at.isoformat(),
        },
    )
    return token, token_plain


def _resolve_asset_source_path(asset: ContentAsset) -> Path:
    if not asset.storage_path:
        raise DomainAPIException(
            code="content.asset.source_missing",
            message="Asset storage path is not configured.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        candidate = resolve_storage_path(asset.storage_path)
    except ValueError as exc:
        raise DomainAPIException(
            code="content.asset.source_invalid",
            message="Asset storage path is outside allowed media root.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not candidate.exists() or not candidate.is_file():
        raise DomainAPIException(
            code="content.asset.source_not_found",
            message="Asset source file not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return candidate


def _create_watermark_text(*, tenant_name: str, username: str) -> str:
    return f"{tenant_name} | {username} | {timezone.now().isoformat()}"


def _record_download_request_log(
    *, organization, user, asset: ContentAsset, status: str
):
    ContentDownloadRequestLog.objects.create(
        organization=organization,
        user=user,
        asset=asset,
        status=status,
    )


def _apply_image_watermark(
    *, source_path: Path, output_path: Path, watermark_text: str
):
    image = Image.open(source_path).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    draw.text((16, 16), watermark_text, fill=(255, 0, 0, 140), font=font)
    draw.text(
        (16, max(32, image.height - 28)),
        watermark_text,
        fill=(255, 0, 0, 110),
        font=font,
    )
    merged = Image.alpha_composite(image, overlay).convert("RGB")
    merged.save(output_path)


def _apply_pdf_watermark(*, source_path: Path, output_path: Path, watermark_text: str):
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source_path))
    writer = PdfWriter()

    for page in reader.pages:
        width = int(float(page.mediabox.width))
        height = int(float(page.mediabox.height))
        wm_image = Image.new(
            "RGBA", (max(width, 200), max(height, 200)), (255, 255, 255, 0)
        )
        draw = ImageDraw.Draw(wm_image)
        font = ImageFont.load_default()
        draw.text((24, 24), watermark_text, fill=(255, 0, 0, 100), font=font)
        draw.text(
            (24, max(48, height - 36)), watermark_text, fill=(255, 0, 0, 100), font=font
        )

        stamp_pdf_bytes = io.BytesIO()
        wm_image.convert("RGB").save(stamp_pdf_bytes, format="PDF")
        stamp_pdf_bytes.seek(0)
        stamp_page = PdfReader(stamp_pdf_bytes).pages[0]

        page.merge_page(stamp_page)
        writer.add_page(page)

    with open(output_path, "wb") as output_file:
        writer.write(output_file)


def _artifact_output_path(
    *, source_path: Path, organization_id: int, user_id: int, asset_id: int
) -> Path:
    export_root = Path(settings.EXPORT_ROOT).resolve()
    target_root = (export_root / "content_downloads").resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    suffix = source_path.suffix.lower() or ".bin"
    name = f"org{organization_id}_asset{asset_id}_user{user_id}_{int(timezone.now().timestamp())}{suffix}"
    return (target_root / name).resolve()


def generate_secured_download_artifact(
    *, organization, user, token_value: str, request
):
    token = (
        ContentDownloadToken.objects.select_related("asset", "user")
        .filter(
            organization=organization,
            token_hash=_sha256(token_value),
        )
        .first()
    )
    if token is None:
        raise DomainAPIException(
            code="content.download_token.invalid",
            message="Download token is invalid.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if token.user_id != user.id:
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="forbidden_owner",
        )
        raise DomainAPIException(
            code="content.download_token.forbidden",
            message="Download token does not belong to this user.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    now = timezone.now()
    if token.expires_at <= now:
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="token_expired",
        )
        raise DomainAPIException(
            code="content.download_token.expired",
            message="Download token has expired.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if (
        token.purpose == DownloadTokenPurpose.DOWNLOAD
        and not token.asset.allow_download
    ):
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="download_disabled",
        )
        raise DomainAPIException(
            code="content.download.permission_denied",
            message="Download is disabled for this asset.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if token.purpose == DownloadTokenPurpose.SHARE and not token.asset.allow_share:
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="share_disabled",
        )
        raise DomainAPIException(
            code="content.share.permission_denied",
            message="Share is disabled for this asset.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    one_minute_ago = now - timedelta(minutes=1)
    request_count = ContentDownloadRequestLog.objects.filter(
        organization=organization,
        user=user,
        requested_at__gte=one_minute_ago,
    ).count()
    if request_count >= 60:
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="rate_limited",
        )
        raise DomainAPIException(
            code="content.download.rate_limited",
            message="Download rate limit exceeded (60 requests per minute).",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if token.asset.state != AssetState.PUBLISHED:
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="asset_unpublished",
        )
        raise DomainAPIException(
            code="content.asset.not_published",
            message="Asset is no longer published.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    role_codes = set(
        organization.user_roles.filter(user=user, is_active=True).values_list(
            "role__code", flat=True
        )
    )
    if not user_has_asset_acl_access(
        user=user, role_codes=role_codes, asset=token.asset
    ):
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="acl_revoked",
        )
        raise DomainAPIException(
            code="content.access.denied",
            message="Asset access denied by chapter ACL coverage.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not _is_manager_role(role_codes) and not user_has_entitlement(
        organization=organization,
        user=user,
        asset=token.asset,
    ):
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="entitlement_revoked",
        )
        raise DomainAPIException(
            code="content.entitlement.required",
            message="Entitlement has been revoked.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    try:
        source_path = _resolve_asset_source_path(token.asset)
        output_path = _artifact_output_path(
            source_path=source_path,
            organization_id=organization.id,
            user_id=user.id,
            asset_id=token.asset_id,
        )

        watermark_text = _create_watermark_text(
            tenant_name=organization.name,
            username=user.username,
        )
        suffix = source_path.suffix.lower()

        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            _apply_image_watermark(
                source_path=source_path,
                output_path=output_path,
                watermark_text=watermark_text,
            )
            mime_type = "image/png" if suffix == ".png" else "image/jpeg"
        elif suffix == ".pdf":
            _apply_pdf_watermark(
                source_path=source_path,
                output_path=output_path,
                watermark_text=watermark_text,
            )
            mime_type = "application/pdf"
        else:
            raise DomainAPIException(
                code="content.download.unsupported_type",
                message="Only image and PDF assets are supported by secured download.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    except DomainAPIException as exc:
        denial_log_status = {
            "content.asset.source_missing": "source_missing",
            "content.asset.source_invalid": "source_invalid",
            "content.asset.source_not_found": "source_not_found",
            "content.download.unsupported_type": "unsupported_type",
        }.get(exc.code, "denied")
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status=denial_log_status,
        )
        raise

    with transaction.atomic():
        artifact = ContentArtifact.objects.create(
            organization=organization,
            asset=token.asset,
            user=user,
            token=token,
            source_path=str(source_path),
            artifact_path=str(output_path),
            mime_type=mime_type,
        )
        _record_download_request_log(
            organization=organization,
            user=user,
            asset=token.asset,
            status="served",
        )

    log_audit_event(
        action="content.download.secured",
        organization=organization,
        actor_user=user,
        request=request,
        resource_type="content_artifact",
        resource_id=str(artifact.id),
        metadata={
            "asset_id": token.asset_id,
            "token_id": token.id,
            "mime_type": mime_type,
        },
    )
    return artifact
