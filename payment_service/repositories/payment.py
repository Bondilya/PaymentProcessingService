from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.enums import Currency, PaymentStatus
from payment_service.domain.models import Payment
from payment_service.infrastructure.models import PaymentModel


class PaymentRepository:
    """SQLAlchemy repository for payment entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        """Retrieve a payment by its primary key."""
        stmt = select(PaymentModel).where(PaymentModel.id == payment_id)
        row = await self._session.scalar(stmt)
        return _to_domain(row) if row else None

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        """Retrieve a payment by its idempotency key."""
        stmt = select(PaymentModel).where(PaymentModel.idempotency_key == key)
        row = await self._session.scalar(stmt)
        return _to_domain(row) if row else None

    async def add(
        self,
        *,
        amount: Decimal,
        currency: Currency,
        description: str,
        metadata: dict[str, object],
        idempotency_key: str,
        webhook_url: str,
    ) -> Payment:
        """Insert a new payment record."""
        row = PaymentModel(
            id=uuid4(),
            amount=amount,
            currency=currency.value,
            description=description,
            metadata_=metadata,
            status=PaymentStatus.PENDING.value,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def claim_processing(self, payment_id: UUID) -> Payment | None:
        """Atomically claim a PENDING payment for processing.

        Transitions ``PENDING`` → ``PROCESSING`` in a single statement and
        returns the updated domain entity, or ``None`` if no row was
        affected (already claimed by another handler).

        Args:
            payment_id: UUID of the payment to claim.

        Returns:
            The updated :class:`Payment` entity, or ``None``.
        """
        stmt = (
            update(PaymentModel)
            .where(
                PaymentModel.id == payment_id,
                PaymentModel.status == PaymentStatus.PENDING.value,
            )
            .values(status=PaymentStatus.PROCESSING.value)
            .returning(PaymentModel)
        )
        result: Any = await self._session.execute(stmt)
        row = result.scalar()
        return _to_domain(row) if row else None

    async def claim_finalization(
        self,
        payment_id: UUID,
        status: PaymentStatus,
        processed_at: datetime,
    ) -> Payment | None:
        """Atomically claim a PROCESSING payment for finalization.

        Transitions ``PROCESSING`` → ``SUCCEEDED`` or ``FAILED`` in a
        single statement and returns the updated domain entity, or
        ``None`` if no row was affected (already claimed by another
        handler).

        Args:
            payment_id: UUID of the payment to finalize.
            status: Target status — ``SUCCEEDED`` or ``FAILED``.
            processed_at: Timestamp to store in the ``processed_at`` column.

        Returns:
            The updated :class:`Payment` entity, or ``None``.
        """
        stmt = (
            update(PaymentModel)
            .where(
                PaymentModel.id == payment_id,
                PaymentModel.status == PaymentStatus.PROCESSING.value,
            )
            .values(status=status.value, processed_at=processed_at)
            .returning(PaymentModel)
        )
        result: Any = await self._session.execute(stmt)
        row = result.scalar()
        return _to_domain(row) if row else None


def _to_domain(row: PaymentModel) -> Payment:
    """Convert a class `PaymentModel` row to a class `Payment` entity."""
    return Payment(
        id_=row.id,
        amount=row.amount,
        currency=Currency(row.currency),
        description=row.description,
        metadata=dict(row.metadata_),
        status=PaymentStatus(row.status),
        idempotency_key=row.idempotency_key,
        webhook_url=row.webhook_url,
        created_at=row.created_at,
        processed_at=row.processed_at,
    )
