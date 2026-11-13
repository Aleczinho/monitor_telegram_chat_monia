import hashlib
import json
import logging
import re
import sqlite3

import aiosqlite
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.handlers import format_event
from app.models import GitHubPayload
from app.queue_store import QueueStore
from app.security import normalize_delivery_id, verify_github_signature

logger = logging.getLogger(__name__)
router = APIRouter()
_EVENT_PATTERN = re.compile(r"[a-z_]{1,64}\Z")


async def _read_limited_body(request: Request, limit: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="Invalid Content-Length")
        if declared_length > limit:
            raise HTTPException(status_code=413, detail="Webhook payload is too large")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail="Webhook payload is too large")
        body.extend(chunk)
    return bytes(body)


@router.post("/webhooks/github", status_code=202)
async def receive_github_webhook(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    queue: QueueStore = request.app.state.queue
    body = await _read_limited_body(request, settings.webhook_max_body_bytes)
    signature = request.headers.get("x-hub-signature-256")
    if not verify_github_signature(settings.require_webhook_secret(), signature, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_type = request.headers.get("x-github-event", "")
    if not _EVENT_PATTERN.fullmatch(event_type):
        raise HTTPException(status_code=400, detail="Missing or invalid event type")

    delivery_id = normalize_delivery_id(request.headers.get("x-github-delivery"))
    if delivery_id is None:
        raise HTTPException(status_code=400, detail="Missing or invalid delivery ID")

    try:
        raw_payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object")

    try:
        payload = GitHubPayload.model_validate(raw_payload)
    except ValidationError as exc:
        logger.warning(
            "webhook_payload_invalid",
            extra={"delivery_id": delivery_id, "event_type": event_type},
        )
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    if payload.repository.full_name.casefold() != settings.github_repository.casefold():
        logger.warning(
            "webhook_repository_rejected",
            extra={"delivery_id": delivery_id, "event_type": event_type},
        )
        raise HTTPException(status_code=403, detail="Repository is not allowed")

    message = format_event(event_type, payload)
    try:
        result = await queue.enqueue(
            delivery_id,
            hashlib.sha256(body).hexdigest(),
            event_type,
            message,
        )
    except (aiosqlite.Error, OSError, sqlite3.Error) as exc:
        logger.error(
            "webhook_queue_unavailable",
            extra={
                "delivery_id": delivery_id,
                "event_type": event_type,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(status_code=503, detail="Event queue unavailable") from exc

    if not result.inserted:
        logger.info(
            "webhook_duplicate",
            extra={
                "delivery_id": delivery_id,
                "event_type": event_type,
                "status": "duplicate",
            },
        )
        return {"status": "duplicate", "delivery_id": delivery_id}

    logger.info(
        "webhook_accepted",
        extra={
            "delivery_id": delivery_id,
            "event_type": event_type,
            "status": result.status,
        },
    )
    return {"status": result.status, "delivery_id": delivery_id}
