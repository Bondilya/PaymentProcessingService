from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.models import OutboxMessage
from payment_service.infrastructure.models import OutboxModel


class OutboxRepository:
    """SQLAlchemy repository for persisting and publishing outbox messages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        aggregate_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> OutboxMessage:
        """Insert a new outbox message and return the domain entity."""
        row = OutboxModel(
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def get_unpublished(self, limit: int = 100) -> list[OutboxMessage]:
        """Return up to *limit* unpublished messages.

        Uses ``SELECT ... FOR UPDATE SKIP LOCKED`` so that multiple
        publishers can safely compete for the same rows.

        Args:
            limit: Maximum number of rows to fetch (default 100).

        Returns:
            A list of :class:`OutboxMessage` entities ordered by
            :attr:`created_at` ascending.
        """
        stmt = (
            select(OutboxModel)
            .where(OutboxModel.published_at.is_(None))
            .order_by(OutboxModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.scalars(stmt)
        return [_to_domain(r) for r in result]

    async def mark_published(self, outbox_id: int, *, published_at: datetime) -> None:
        """Mark a single outbox message as published."""
        stmt = (
            update(OutboxModel)
            .where(OutboxModel.id == outbox_id)
            .values(published_at=published_at)
        )
        await self._session.execute(stmt)


def _to_domain(row: OutboxModel) -> OutboxMessage:
    """Convert an :class:`OutboxModel` row to an :class:`OutboxMessage`."""
    return OutboxMessage(
        id_=row.id,
        aggregate_id=row.aggregate_id,
        event_type=row.event_type,
        payload=dict(row.payload),
        created_at=row.created_at,
        published_at=row.published_at,
    )
