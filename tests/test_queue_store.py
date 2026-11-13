import time

import aiosqlite
import pytest

from app.queue_store import QueueStore
from tests.conftest import body_digest


@pytest.mark.asyncio
async def test_delivery_is_deduplicated_and_persisted(tmp_path):
    database_path = tmp_path / "events.sqlite3"
    queue = QueueStore(database_path)
    await queue.initialize()

    digest = body_digest("payload-1")
    first = await queue.enqueue("delivery-1", digest, "pull_request", "<b>PR</b>")
    duplicate = await queue.enqueue("delivery-1", digest, "pull_request", "<b>PR</b>")

    assert first.inserted
    assert first.status == "pending"
    assert not duplicate.inserted

    reopened = QueueStore(database_path)
    await reopened.initialize()
    assert await reopened.counts() == {"pending": 1}


@pytest.mark.asyncio
async def test_same_body_with_a_different_delivery_id_is_deduplicated(tmp_path):
    queue = QueueStore(tmp_path / "events.sqlite3")
    await queue.initialize()
    digest = body_digest("replayed-payload")

    first = await queue.enqueue("delivery-original", digest, "pull_request", "message")
    replay = await queue.enqueue("delivery-replay", digest, "pull_request", "message")

    assert first.inserted
    assert not replay.inserted
    assert await queue.counts() == {"pending": 1}


@pytest.mark.asyncio
async def test_unsupported_event_is_persisted_as_ignored(tmp_path):
    queue = QueueStore(tmp_path / "events.sqlite3")
    await queue.initialize()

    result = await queue.enqueue(
        "delivery-ignored",
        body_digest("ignored-payload"),
        "push",
        None,
    )

    assert result.inserted
    assert result.status == "ignored"
    assert await queue.claim_next(lease_seconds=10) is None
    assert await queue.counts() == {"ignored": 1}


@pytest.mark.asyncio
async def test_expired_processing_lease_can_be_reclaimed(tmp_path):
    database_path = tmp_path / "events.sqlite3"
    queue = QueueStore(database_path)
    await queue.initialize()
    await queue.enqueue(
        "delivery-lease",
        body_digest("lease-payload"),
        "pull_request",
        "message",
    )

    first_claim = await queue.claim_next(lease_seconds=60)
    assert first_claim is not None
    assert first_claim.attempts == 1

    async with aiosqlite.connect(database_path) as connection:
        await connection.execute(
            "UPDATE webhook_events SET lease_until = ? WHERE delivery_id = ?",
            (time.time() - 1, "delivery-lease"),
        )
        await connection.commit()

    second_claim = await queue.claim_next(lease_seconds=60)
    assert second_claim is not None
    assert second_claim.attempts == 2


@pytest.mark.asyncio
async def test_retryable_failure_is_rescheduled_and_permanent_failure_stops(tmp_path):
    queue = QueueStore(tmp_path / "events.sqlite3")
    await queue.initialize()
    await queue.enqueue(
        "delivery-retry",
        body_digest("retry-payload"),
        "pull_request",
        "message",
    )
    item = await queue.claim_next(lease_seconds=60)
    assert item is not None

    status = await queue.record_failure(
        item,
        "telegram_rate_limited",
        retry_delay=60,
        max_attempts=3,
        retryable=True,
    )
    assert status == "pending"
    assert await queue.claim_next(lease_seconds=60) is None

    async with aiosqlite.connect(queue.path) as connection:
        await connection.execute(
            "UPDATE webhook_events SET available_at = 0 WHERE delivery_id = ?",
            ("delivery-retry",),
        )
        await connection.commit()
    item = await queue.claim_next(lease_seconds=60)
    assert item is not None

    status = await queue.record_failure(
        item,
        "telegram_bad_request",
        retry_delay=0,
        max_attempts=3,
        retryable=False,
    )
    assert status == "failed"
    assert await queue.counts() == {"failed": 1}


@pytest.mark.asyncio
async def test_sent_rows_are_removed_only_after_dedup_retention(tmp_path):
    queue = QueueStore(tmp_path / "events.sqlite3", retention_days=30)
    await queue.initialize()
    await queue.enqueue(
        "delivery-old",
        body_digest("old-payload"),
        "push",
        None,
    )
    async with aiosqlite.connect(queue.path) as connection:
        await connection.execute(
            "UPDATE webhook_events SET status = 'sent', received_at = ? WHERE delivery_id = ?",
            (time.time() - 31 * 86400, "delivery-old"),
        )
        await connection.commit()

    removed = await queue.purge_old_completed()

    assert removed == 1
    assert await queue.counts() == {}
