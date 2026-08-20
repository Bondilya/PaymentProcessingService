from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.consumer.payment_processor import PaymentProcessor
from payment_service.domain.enums import Currency, PaymentStatus
from payment_service.repositories.outbox import OutboxRepository
from payment_service.repositories.payment import PaymentRepository


@pytest.fixture()
def processor(
    sqlite_session_factory: async_sessionmaker[AsyncSession],
    mock_gateway: MagicMock,
    mock_webhook_sender: MagicMock,
) -> PaymentProcessor:
    """Return a :class:`PaymentProcessor` with mock collaborators."""
    return PaymentProcessor(
        session_factory=sqlite_session_factory,
        gateway=mock_gateway,
        webhook_sender=mock_webhook_sender,
    )


async def _seed_payment(
    session: AsyncSession,
    *,
    idempotency_key: str = "key-001",
    status: PaymentStatus = PaymentStatus.PENDING,
) -> UUID:
    """Insert a payment row and return its ID."""
    repo = PaymentRepository(session)
    payment = await repo.add(
        amount=Decimal("100.00"),
        currency=Currency.USD,
        description="Test",
        metadata={"k": "v"},
        idempotency_key=idempotency_key,
        webhook_url="https://example.com/webhook",
    )
    if status != PaymentStatus.PENDING:
        from sqlalchemy import update as sa_update

        from payment_service.infrastructure.models import PaymentModel

        stmt = sa_update(PaymentModel).where(PaymentModel.id == payment.id).values(status=status.value)
        await session.execute(stmt)
    await session.commit()
    return payment.id


class TestPaymentProcessor:
    """Tests for :class:`PaymentProcessor`."""

    @pytest.mark.asyncio
    async def test_process_success(
        self,
        processor: PaymentProcessor,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
        mock_gateway: MagicMock,
        mock_webhook_sender: MagicMock,
    ) -> None:
        """Should mark payment as ``succeeded`` and send webhook."""
        async with sqlite_session_factory() as session:
            payment_id = await _seed_payment(session)

        await processor.process(str(payment_id))

        async with sqlite_session_factory() as session:
            repo = PaymentRepository(session)
            payment = await repo.get_by_id(payment_id)
            assert payment is not None
            assert payment.status == PaymentStatus.SUCCEEDED
            assert payment.processed_at is not None

        mock_gateway.process.assert_called_once()
        mock_webhook_sender.send.assert_called_once()
        webhook_payload = mock_webhook_sender.send.call_args[0][1]
        assert webhook_payload["payment_id"] == str(payment_id)
        assert webhook_payload["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_process_failure(
        self,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
        failing_gateway: MagicMock,
        mock_webhook_sender: MagicMock,
    ) -> None:
        """Should mark payment as ``failed`` when gateway declines."""
        processor = PaymentProcessor(
            session_factory=sqlite_session_factory,
            gateway=failing_gateway,
            webhook_sender=mock_webhook_sender,
        )
        async with sqlite_session_factory() as session:
            payment_id = await _seed_payment(session, idempotency_key="key-fail")

        await processor.process(str(payment_id))

        async with sqlite_session_factory() as session:
            repo = PaymentRepository(session)
            payment = await repo.get_by_id(payment_id)
            assert payment is not None
            assert payment.status == PaymentStatus.FAILED

        mock_webhook_sender.send.assert_called_once()
        webhook_payload = mock_webhook_sender.send.call_args[0][1]
        assert webhook_payload["status"] == "failed"

    @pytest.mark.asyncio
    async def test_process_nonexistent_payment(
        self,
        processor: PaymentProcessor,
        mock_gateway: MagicMock,
    ) -> None:
        """Should skip processing when payment does not exist."""
        from uuid import uuid4

        await processor.process(str(uuid4()))
        mock_gateway.process.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_already_processed(
        self,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
        mock_gateway: MagicMock,
        mock_webhook_sender: MagicMock,
    ) -> None:
        """Should skip when payment is already ``succeeded``."""
        processor = PaymentProcessor(
            session_factory=sqlite_session_factory,
            gateway=mock_gateway,
            webhook_sender=mock_webhook_sender,
        )
        async with sqlite_session_factory() as session:
            payment_id = await _seed_payment(
                session,
                idempotency_key="key-done",
                status=PaymentStatus.SUCCEEDED,
            )

        await processor.process(str(payment_id))
        mock_gateway.process.assert_not_called()

    @pytest.mark.asyncio
    async def test_webhook_called_even_on_failure(
        self,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
        failing_gateway: MagicMock,
        failing_webhook_sender: MagicMock,
    ) -> None:
        """Should attempt webhook delivery even when payment fails."""
        processor = PaymentProcessor(
            session_factory=sqlite_session_factory,
            gateway=failing_gateway,
            webhook_sender=failing_webhook_sender,
        )
        async with sqlite_session_factory() as session:
            payment_id = await _seed_payment(
                session,
                idempotency_key="key-fail-wh",
            )

        await processor.process(str(payment_id))
        failing_webhook_sender.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_with_outbox(
        self,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
        mock_gateway: MagicMock,
        mock_webhook_sender: MagicMock,
    ) -> None:
        """Should not affect outbox records during processing."""
        processor = PaymentProcessor(
            session_factory=sqlite_session_factory,
            gateway=mock_gateway,
            webhook_sender=mock_webhook_sender,
        )
        async with sqlite_session_factory() as session:
            payment_id = await _seed_payment(session, idempotency_key="key-ob")
            outbox_repo = OutboxRepository(session)
            await outbox_repo.add(
                aggregate_id=payment_id,
                event_type="payment.created",
                payload={"payment_id": str(payment_id)},
            )
            await session.commit()

        await processor.process(str(payment_id))

        async with sqlite_session_factory() as session:
            outbox_repo = OutboxRepository(session)
            messages = await outbox_repo.get_unpublished()
            assert len(messages) == 1
            assert messages[0].aggregate_id == payment_id
