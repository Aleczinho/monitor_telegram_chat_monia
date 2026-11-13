import asyncio
import logging
import random
import time

from app.config import Settings
from app.logging_config import configure_logging
from app.queue_store import QueueItem, QueueStore
from app.telegram import TelegramClient, TelegramError

logger = logging.getLogger(__name__)


class TelegramWorker:
    def __init__(
        self,
        settings: Settings,
        queue: QueueStore,
        telegram: TelegramClient,
    ) -> None:
        self.settings = settings
        self.queue = queue
        self.telegram = telegram

    async def run_once(self) -> bool:
        item = await self.queue.claim_next(self.settings.worker_lease_seconds)
        if item is None:
            return False

        try:
            await self.telegram.send_message(item.message_html)
        except TelegramError as error:
            retry_delay = self._retry_delay(item, error)
            status = await self.queue.record_failure(
                item,
                error.code,
                retry_delay,
                self.settings.worker_max_attempts,
                error.retryable,
            )
            logger.log(
                logging.WARNING if status == "pending" else logging.ERROR,
                "telegram_delivery_failed",
                extra={
                    "delivery_id": item.delivery_id,
                    "event_type": item.event_type,
                    "status": status,
                    "attempts": item.attempts,
                    "error_type": error.code,
                },
            )
        else:
            await self.queue.mark_sent(item.delivery_id)
            logger.info(
                "telegram_delivery_sent",
                extra={
                    "delivery_id": item.delivery_id,
                    "event_type": item.event_type,
                    "status": "sent",
                    "attempts": item.attempts,
                },
            )
        return True

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        next_cleanup = time.monotonic() + 86400
        while not stop.is_set():
            processed = await self.run_once()
            if not processed:
                try:
                    await asyncio.wait_for(
                        stop.wait(),
                        timeout=self.settings.worker_poll_interval_seconds,
                    )
                except TimeoutError:
                    pass
            if time.monotonic() >= next_cleanup:
                await self.queue.purge_old_completed()
                next_cleanup = time.monotonic() + 86400

    def _retry_delay(self, item: QueueItem, error: TelegramError) -> float:
        if error.retry_after is not None:
            return error.retry_after
        ceiling = min(
            self.settings.worker_retry_base_seconds * (2 ** (item.attempts - 1)),
            3600,
        )
        return random.uniform(0.8 * ceiling, 1.2 * ceiling)


async def run_worker() -> None:
    settings = Settings()
    settings.require_telegram_credentials()
    configure_logging(settings.log_level)
    queue = QueueStore(settings.database_path, settings.dedup_retention_days)
    await queue.initialize()
    async with TelegramClient(settings) as telegram:
        worker = TelegramWorker(settings, queue, telegram)
        await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(run_worker())
