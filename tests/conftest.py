import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

WEBHOOK_SECRET = "test-webhook-secret"
DELIVERY_ID = "b9c9b12e-8f20-4b54-a8b8-52b58cf73dfa"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        app_env="test",
        github_webhook_secret=WEBHOOK_SECRET,
        github_repository="healthdevio/projeto-itia-dois",
        telegram_bot_token="123456:test-token",
        telegram_chat_id="-1001234567890",
        database_path=tmp_path / "events.sqlite3",
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def pull_request_payload():
    return {
        "repository": {"full_name": "healthdevio/projeto-itia-dois"},
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Implementar autenticação",
            "html_url": "https://github.com/healthdevio/projeto-itia-dois/pull/42",
            "user": {"login": "dev-alice"},
            "head": {"ref": "feat/authentication"},
            "base": {"ref": "develop"},
            "created_at": "2026-11-13T10:00:00Z",
            "updated_at": "2026-11-13T10:00:00Z",
            "merged": False,
        },
    }


def signed_headers(body: bytes, event_type: str, delivery_id: str | None = None) -> dict[str, str]:
    import hashlib
    import hmac

    signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": f"sha256={signature}",
        "X-GitHub-Event": event_type,
        "X-GitHub-Delivery": delivery_id or str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


def json_body(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def body_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
