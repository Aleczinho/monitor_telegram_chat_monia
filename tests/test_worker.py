import pytest

from app.queue_store import QueueStore
from app.telegram import TelegramError
from app.worker import TelegramWorker
from tests.conftest import body_digest


class FakeTelegram:
    def __init__(self, error: TelegramError | None = None) -> None:
        self.error = error
        self.messages: list[str] = []

    async def send_message(self, message_html: str) -> None:
        self.messages.append(message_html)
        if self.error is not None:
            raise self.error


@pytest.mark.asyncio
async def test_worker_sends_and_marks_event_sent(settings):
    queue = QueueStore(settings.database_path)
    await queue.initialize()
    await queue.enqueue(
        "delivery-worker",
        body_digest("worker-payload"),
        "pull_request",
        "<b>PR</b>",
    )
    telegram = FakeTelegram()
    worker = TelegramWorker(settings, queue, telegram)

    processed = await worker.run_once()

    assert processed
    assert telegram.messages == ["<b>PR</b>"]
    assert await queue.counts() == {"sent": 1}


@pytest.mark.asyncio
async def test_worker_reschedules_transient_telegram_error(settings):
    queue = QueueStore(settings.database_path)
    await queue.initialize()
    await queue.enqueue(
        "delivery-retry-worker",
        body_digest("retry-worker-payload"),
        "pull_request",
        "message",
    )
    telegram = FakeTelegram(
        TelegramError(
            "telegram_rate_limited",
            retryable=True,
            retry_after=30,
        )
    )
    worker = TelegramWorker(settings, queue, telegram)

    processed = await worker.run_once()

    assert processed
    assert await queue.counts() == {"pending": 1}


@pytest.mark.asyncio
async def test_worker_marks_permanent_telegram_error_failed(settings):
    queue = QueueStore(settings.database_path)
    await queue.initialize()
    await queue.enqueue(
        "delivery-failed-worker",
        body_digest("failed-worker-payload"),
        "pull_request",
        "message",
    )
    telegram = FakeTelegram(
        TelegramError("telegram_bad_request", retryable=False),
    )
    worker = TelegramWorker(settings, queue, telegram)

    processed = await worker.run_once()

    assert processed
    assert await queue.counts() == {"failed": 1}
