import hashlib
import hmac

from app.security import normalize_delivery_id, verify_github_signature


def _signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_accepts_signature_for_exact_raw_body():
    body = b'{"action":"opened"}'

    assert verify_github_signature("secret", _signature("secret", body), body)


def test_rejects_signature_if_body_changes():
    signature = _signature("secret", b'{"action":"opened"}')

    assert not verify_github_signature("secret", signature, b'{"action":"closed"}')


def test_rejects_missing_or_malformed_signature():
    assert not verify_github_signature("secret", None, b"{}")
    assert not verify_github_signature("secret", "sha1=not-a-signature", b"{}")
    assert not verify_github_signature("secret", "sha256=xyz", b"{}")


def test_normalizes_uuid_delivery_id_and_rejects_invalid_values():
    assert (
        normalize_delivery_id("B9C9B12E-8F20-4B54-A8B8-52B58CF73DFA")
        == "b9c9b12e-8f20-4b54-a8b8-52b58cf73dfa"
    )
    assert normalize_delivery_id("not-a-uuid") is None
    assert normalize_delivery_id(None) is None
