import json
import sqlite3
import uuid

from tests.conftest import DELIVERY_ID, json_body, signed_headers


def test_valid_pull_request_webhook_is_queued(client, pull_request_payload):
    body = json_body(pull_request_payload)
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, "pull_request", DELIVERY_ID),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "pending", "delivery_id": DELIVERY_ID}


def test_duplicate_delivery_is_accepted_without_a_second_queue_item(
    client,
    pull_request_payload,
):
    body = json_body(pull_request_payload)
    headers = signed_headers(body, "pull_request", DELIVERY_ID)

    first = client.post("/webhooks/github", content=body, headers=headers)
    second = client.post("/webhooks/github", content=body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"


def test_same_signed_body_with_new_delivery_id_is_deduplicated(
    client,
    pull_request_payload,
):
    body = json_body(pull_request_payload)
    first = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, "pull_request", DELIVERY_ID),
    )
    replay = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, "pull_request", str(uuid.uuid4())),
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json()["status"] == "duplicate"


def test_invalid_signature_is_rejected(client, pull_request_payload):
    body = json_body(pull_request_payload)
    headers = signed_headers(body, "pull_request", DELIVERY_ID)
    headers["X-Hub-Signature-256"] = "sha256=" + "0" * 64

    response = client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 401


def test_malformed_json_with_valid_signature_is_rejected(client):
    body = b'{"repository":'
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, "pull_request", DELIVERY_ID),
    )
    assert response.status_code == 400


def test_invalid_delivery_id_is_rejected(client, pull_request_payload):
    body = json_body(pull_request_payload)

    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, "pull_request", "not-a-uuid"),
    )

    assert response.status_code == 400


def test_repository_outside_allowlist_is_rejected(client, pull_request_payload):
    pull_request_payload["repository"]["full_name"] = "other/repository"
    body = json_body(pull_request_payload)

    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, "pull_request", DELIVERY_ID),
    )

    assert response.status_code == 403


def test_unsupported_event_is_recorded_as_ignored(client):
    body = json_body({"repository": {"full_name": "healthdevio/projeto-itia-dois"}})

    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, "push", str(uuid.uuid4())),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


def test_oversized_body_is_rejected(app, settings):
    settings.webhook_max_body_bytes = 1024
    payload = {
        "repository": {"full_name": "healthdevio/projeto-itia-dois"},
        "padding": "x" * 1100,
    }
    body = json.dumps(payload).encode()
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers=signed_headers(body, "push", DELIVERY_ID),
        )

    assert response.status_code == 413


def test_database_failure_returns_503(client, pull_request_payload, monkeypatch):
    async def fail_enqueue(*_: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(client.app.state.queue, "enqueue", fail_enqueue)
    body = json_body(pull_request_payload)

    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, "pull_request", DELIVERY_ID),
    )

    assert response.status_code == 503


def test_health_endpoints_do_not_require_telegram_reachability(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {
        "status": "ready",
        "dependencies": {"sqlite": "ok"},
    }
