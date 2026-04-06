from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key_material = getattr(settings, "DATA_ENCRYPTION_KEY", None)
    if not key_material:
        if not getattr(settings, "DEBUG", False):
            raise ImproperlyConfigured(
                "DATA_ENCRYPTION_KEY must be configured when DEBUG is False."
            )
        raise ImproperlyConfigured("DATA_ENCRYPTION_KEY is not configured.")

    digest = hashlib.sha256(key_material.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_pii_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_pii_value(value: str) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Encrypted value cannot be decrypted.") from exc


def mask_text(value: str, *, keep_start: int = 2, keep_end: int = 0) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= keep_start + keep_end:
        return "*" * len(text)
    return f"{text[:keep_start]}{'*' * (len(text) - keep_start - keep_end)}{text[-keep_end:] if keep_end else ''}"


def mask_phone(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 4:
        return f"***-***-{digits[-4:]}"
    return "*" * max(len(raw), 4)


def mask_postal_code(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 3:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 3)}"
