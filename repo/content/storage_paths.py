from pathlib import Path

from django.conf import settings


def normalize_storage_path(value: str) -> str:
    raw_value = (value or "").strip()
    if not raw_value:
        return ""

    normalized = raw_value.replace("\\", "/")
    relative_candidate = Path(normalized)
    if relative_candidate.is_absolute():
        raise ValueError("storage_path must be a relative path.")

    media_root = Path(settings.MEDIA_ROOT).resolve()
    resolved = (media_root / relative_candidate).resolve()
    try:
        relative_resolved = resolved.relative_to(media_root)
    except ValueError as exc:
        raise ValueError(
            "storage_path must resolve inside the allowed media root."
        ) from exc

    if str(relative_resolved) == ".":
        raise ValueError("storage_path must point to a file path.")

    return relative_resolved.as_posix()


def resolve_storage_path(storage_path: str) -> Path:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    normalized = normalize_storage_path(storage_path)
    return (media_root / normalized).resolve()
