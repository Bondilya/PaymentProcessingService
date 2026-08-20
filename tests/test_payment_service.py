from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.api.v1.service import PaymentService
from payment_service.domain.enums import Currency, PaymentStatus
from payment_service.infrastructure.database import SqlAlchemyUnitOfWork
from payment_service.repositories.outbox import OutboxRepository
from payment_service.repositories.payment import PaymentRepository


@pytest.fixture()
def service(
    db_session: AsyncSession,
) -> PaymentService:
    """Return a :class:`PaymentService` backed by SQLite."""
    return PaymentService(SqlAlchemyUnitOfWork(session=db_session))


class TestPaymentService:
    """Tests for :class:`PaymentService`."""

    @pytest.mark.asyncio
    async def test_create_payment(
        self,
        service: PaymentService,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Should create a payment in ``pending`` status."""
        payment = await service.create_payment(
            amount=Decimal("99.99"),
            currency=Currency.USD,
            description="Order #1",
            metadata={"order_id": "ORD-1"},
            idempotency_key="idem-001",
            webhook_url="https://example.com/wh",
        )
        assert isinstance(payment.id, UUID)
        assert payment.status == PaymentStatus.PENDING
        assert payment.amount == Decimal("99.99")
        assert payment.currency == Currency.USD
        assert payment.processed_at is None

    @pytest.mark.asyncio
    async def test_create_payment_writes_outbox(
        self,
        service: PaymentService,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Should create an outbox event in the same transaction."""
        payment = await service.create_payment(
            amount=Decimal("50.00"),
            currency=Currency.EUR,
            description="Order #2",
            metadata={},
            idempotency_key="idem-002",
            webhook_url="https://example.com/wh",
        )
        async with sqlite_session_factory() as session:
            outbox_repo = OutboxRepository(session)
            messages = await outbox_repo.get_unpublished()
            assert len(messages) == 1
            assert messages[0].aggregate_id == payment.id
            assert messages[0].event_type == "payment.created"
            assert messages[0].payload["payment_id"] == str(payment.id)

    @pytest.mark.asyncio
    async def test_idempotent_create_returns_existing(
        self,
        service: PaymentService,
    ) -> None:
        """Should return the existing payment on duplicate idempotency key."""
        first = await service.create_payment(
            amount=Decimal("10.00"),
            currency=Currency.RUB,
            description="First",
            metadata={},
            idempotency_key="dup-key",
            webhook_url="https://example.com/wh",
        )
        second = await service.create_payment(
            amount=Decimal("20.00"),
            currency=Currency.USD,
            description="Second",
            metadata={},
            idempotency_key="dup-key",
            webhook_url="https://example.com/wh2",
        )
        assert first.id == second.id
        assert second.amount == Decimal("10.00")
        assert second.currency == Currency.RUB

    @pytest.mark.asyncio
    async def test_create_multiple_payments_different_keys(
        self,
        service: PaymentService,
    ) -> None:
        """Should create separate payments with different idempotency keys."""
        p1 = await service.create_payment(
            amount=Decimal("1.00"),
            currency=Currency.USD,
            description="A",
            metadata={},
            idempotency_key="key-A",
            webhook_url="https://example.com/wh",
        )
        p2 = await service.create_payment(
            amount=Decimal("2.00"),
            currency=Currency.EUR,
            description="B",
            metadata={},
            idempotency_key="key-B",
            webhook_url="https://example.com/wh",
        )
        assert p1.id != p2.id

    @pytest.mark.asyncio
    async def test_create_payment_with_empty_metadata(
        self,
        service: PaymentService,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Should accept empty metadata."""
        payment = await service.create_payment(
            amount=Decimal("5.00"),
            currency=Currency.RUB,
            description="Empty meta",
            metadata={},
            idempotency_key="key-empty-meta",
            webhook_url="https://example.com/wh",
        )
        assert payment.metadata == {}

    @pytest.mark.asyncio
    async def test_create_payment_with_complex_metadata(
        self,
        service: PaymentService,
    ) -> None:
        """Should accept nested JSON metadata."""
        payment = await service.create_payment(
            amount=Decimal("5.00"),
            currency=Currency.USD,
            description="Complex meta",
            metadata={"nested": {"a": 1, "b": [1, 2, 3]}, "flag": True},
            idempotency_key="key-complex-meta",
            webhook_url="https://example.com/wh",
        )
        assert payment.metadata["nested"]["a"] == 1
        assert payment.metadata["nested"]["b"] == [1, 2, 3]
        assert payment.metadata["flag"] is True

    @pytest.mark.asyncio
    async def test_create_payment_persists_to_db(
        self,
        service: PaymentService,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Should persist the payment to the database."""
        payment = await service.create_payment(
            amount=Decimal("42.00"),
            currency=Currency.USD,
            description="Persisted",
            metadata={"k": "v"},
            idempotency_key="key-persist",
            webhook_url="https://example.com/wh",
        )
        async with sqlite_session_factory() as session:
            repo = PaymentRepository(session)
            found = await repo.get_by_id(payment.id)
            assert found is not None
            assert found.id == payment.id
            assert found.amount == Decimal("42.00")
