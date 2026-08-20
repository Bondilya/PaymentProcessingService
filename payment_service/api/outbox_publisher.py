import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.infrastructure.broker import ROUTING_KEY, payment_exchange
from payment_service.repositories.outbox import OutboxRepository
from payment_service.settings import Outbox

if TYPE_CHECKING:
    from faststream.rabbit import RabbitBroker

logger = logging.getLogger(__name__)


class OutboxPublisher:
    """Relay that drains unpublished outbox events to RabbitMQ."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        broker: "RabbitBroker",
        settings: Outbox,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker
        self._poll_interval = settings.poll_interval
        self._batch_size = settings.batch_size
        self._running = False

    async def start(self) -> None:
        """Start the polling loop (runs until :meth:`stop` is called)."""
        self._running = True
        logger.info("Outbox publisher started (interval=%.1fs)", self._poll_interval)
        while self._running:
            try:
                await self._publish_batch()
            except Exception:
                logger.exception("Outbox publisher error")
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        """Signal the polling loop to stop."""
        self._running = False
        logger.info("Outbox publisher stopping")

    async def _publish_batch(self) -> None:
        """Publish a single batch of unpublished events."""
        async with self._session_factory() as session:
            outbox_repo = OutboxRepository(session)
            messages = await outbox_repo.get_unpublished(limit=self._batch_size)
            if not messages:
                return

            for msg in messages:
                await self._broker.publish(
                    msg.payload,
                    exchange=payment_exchange,
                    routing_key=ROUTING_KEY,
                )
                await outbox_repo.mark_published(msg.id, published_at=datetime.now(UTC))
                await session.commit()
                logger.info("Published outbox event %d (payment %s)", msg.id, msg.aggregate_id)
