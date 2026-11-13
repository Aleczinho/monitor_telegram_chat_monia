import hashlib
import hmac
import re
from uuid import UUID

from pydantic import SecretStr

_SIGNATURE_PATTERN = re.compile(r"sha256=[0-9a-f]{64}\Z")


def verify_github_signature(
    secret: SecretStr | str,
    signature: str | None,
    body: bytes,
) -> bool:
    if signature is None or not _SIGNATURE_PATTERN.fullmatch(signature):
        return False

    secret_value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    expected = (
        "sha256="
        + hmac.new(
            secret_value.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def normalize_delivery_id(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        return None
