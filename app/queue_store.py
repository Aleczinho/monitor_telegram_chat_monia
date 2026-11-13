import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import aiosqlite

QueueStatus = Literal["pending", "processing", "sent", "ignored", "failed"]


@dataclass(frozen=True, slots=True)
class QueueItem:
    delivery_id: str
    event_type: str
    message_html: str
    attempts: int


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    inserted: bool
    status: QueueStatus


class QueueStore:
    def __init__(self, path: Path, retention_days: int = 90) -> None:
        self.path = path
        self.retention_days = retention_days

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(str(self.path), timeout=5.0)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            await connection.close()

    async def initialize(self) -> None:
        await asyncio.to_thread(self.path.parent.mkdir, parents=True, exist_ok=True)
        async with self._connection() as connection:
            await connection.execute("PRAGMA journal_mode = WAL")
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS webhook_events (
                    delivery_id TEXT PRIMARY KEY,
                    body_digest TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'processing', 'sent', 'ignored', 'failed')
                    ),
                    message_html TEXT,
                    received_at REAL NOT NULL,
                    available_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_until REAL,
                    sent_at REAL,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_webhook_events_ready
                    ON webhook_events(status, available_at, lease_until, received_at);
                """
            )
            await connection.commit()

    async def check_ready(self) -> None:
        async with self._connection() as connection:
            async with connection.execute("SELECT COUNT(*) FROM webhook_events") as cursor:
                await cursor.fetchone()

    async def enqueue(
        self,
        delivery_id: str,
        body_digest: str,
        event_type: str,
        message_html: str | None,
    ) -> EnqueueResult:
        now = time.time()
        status: QueueStatus = "pending" if message_html is not None else "ignored"
        async with self._connection() as connection:
            cursor = await connection.execute(
                """
                INSERT OR IGNORE INTO webhook_events (
                    delivery_id, body_digest, event_type, status, message_html,
                    received_at, available_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (delivery_id, body_digest, event_type, status, message_html, now, now),
            )
            await connection.commit()
            return EnqueueResult(inserted=cursor.rowcount == 1, status=status)

    async def claim_next(self, lease_seconds: int) -> QueueItem | None:
        now = time.time()
        async with self._connection() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            async with connection.execute(
                """
                SELECT delivery_id, event_type, message_html, attempts
                FROM webhook_events
                WHERE (status = 'pending' AND available_at <= ?)
                   OR (status = 'processing' AND lease_until <= ?)
                ORDER BY received_at, delivery_id
                LIMIT 1
                """,
                (now, now),
            ) as cursor:
                row = await cursor.fetchone()

            if row is None:
                await connection.commit()
                return None

            await connection.execute(
                """
                UPDATE webhook_events
                SET status = 'processing', attempts = attempts + 1, lease_until = ?
                WHERE delivery_id = ?
                """,
                (now + lease_seconds, row["delivery_id"]),
            )
            await connection.commit()
            if row["message_html"] is None:
                raise RuntimeError("Queued event has no message")
            return QueueItem(
                delivery_id=row["delivery_id"],
                event_type=row["event_type"],
                message_html=row["message_html"],
                attempts=row["attempts"] + 1,
            )

    async def mark_sent(self, delivery_id: str) -> None:
        async with self._connection() as connection:
            cursor = await connection.execute(
                """
                UPDATE webhook_events
                SET status = 'sent', sent_at = ?, lease_until = NULL, last_error = NULL
                WHERE delivery_id = ? AND status = 'processing'
                """,
                (time.time(), delivery_id),
            )
            await connection.commit()
            if cursor.rowcount != 1:
                raise RuntimeError("Could not mark claimed event as sent")

    async def record_failure(
        self,
        item: QueueItem,
        error_code: str,
        retry_delay: float,
        max_attempts: int,
        retryable: bool,
    ) -> QueueStatus:
        status: QueueStatus = "pending" if retryable and item.attempts < max_attempts else "failed"
        available_at = time.time() + retry_delay if status == "pending" else time.time()
        async with self._connection() as connection:
            cursor = await connection.execute(
                """
                UPDATE webhook_events
                SET status = ?, available_at = ?, lease_until = NULL, last_error = ?
                WHERE delivery_id = ? AND status = 'processing'
                """,
                (status, available_at, error_code[:200], item.delivery_id),
            )
            await connection.commit()
            if cursor.rowcount != 1:
                raise RuntimeError("Could not record failure for claimed event")
        return status

    async def purge_old_completed(self, now: float | None = None) -> int:
        cutoff = (time.time() if now is None else now) - self.retention_days * 86400
        async with self._connection() as connection:
            cursor = await connection.execute(
                """
                DELETE FROM webhook_events
                WHERE status IN ('sent', 'ignored') AND received_at < ?
                """,
                (cutoff,),
            )
            await connection.commit()
            return cursor.rowcount

    async def counts(self) -> dict[str, int]:
        async with self._connection() as connection:
            async with connection.execute(
                "SELECT status, COUNT(*) AS count FROM webhook_events GROUP BY status"
            ) as cursor:
                rows = await cursor.fetchall()
        return {row["status"]: row["count"] for row in rows}
