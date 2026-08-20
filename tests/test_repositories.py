from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.enums import Currency, PaymentStatus
from payment_service.repositories.outbox import OutboxRepository
from payment_service.repositories.payment import PaymentRepository


class TestPaymentRepository:
    """Tests for :class:`PaymentRepository`."""

    @pytest.mark.asyncio
    async def test_add_and_get_by_id(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should persist and retrieve a payment by ID."""
        repo = PaymentRepository(db_session)
        payment = await repo.add(
            amount=Decimal("100.00"),
            currency=Currency.USD,
            description="Test",
            metadata={"a": 1},
            idempotency_key="repo-key-1",
            webhook_url="https://example.com/wh",
        )
        await db_session.commit()

        found = await repo.get_by_id(payment.id)
        assert found is not None
        assert found.id == payment.id
        assert found.amount == Decimal("100.00")
        assert found.currency == Currency.USD
        assert found.status == PaymentStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should return ``None`` for a non-existent ID."""
        repo = PaymentRepository(db_session)
        found = await repo.get_by_id(uuid4())
        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_idempotency_key(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should find a payment by its idempotency key."""
        repo = PaymentRepository(db_session)
        await repo.add(
            amount=Decimal("50.00"),
            currency=Currency.EUR,
            description="ByKey",
            metadata={},
            idempotency_key="unique-key-123",
            webhook_url="https://example.com/wh",
        )
        await db_session.commit()

        found = await repo.get_by_idempotency_key("unique-key-123")
        assert found is not None
        assert found.idempotency_key == "unique-key-123"

    @pytest.mark.asyncio
    async def test_get_by_idempotency_key_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should return ``None`` for an unknown idempotency key."""
        repo = PaymentRepository(db_session)
        found = await repo.get_by_idempotency_key("nonexistent")
        assert found is None

    @pytest.mark.asyncio
    async def test_claim_processing_returns_payment(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should claim a PENDING payment and return the domain entity."""
        repo = PaymentRepository(db_session)
        payment = await repo.add(
            amount=Decimal("10.00"),
            currency=Currency.RUB,
            description="ClaimProcessing",
            metadata={},
            idempotency_key="claim-proc-1",
            webhook_url="https://example.com/wh",
        )
        await db_session.commit()

        claimed = await repo.claim_processing(payment.id)
        await db_session.commit()

        assert claimed is not None
        assert claimed.id == payment.id
        assert claimed.status == PaymentStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_claim_processing_already_claimed(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should return None when another handler already claimed the payment."""
        repo = PaymentRepository(db_session)
        payment = await repo.add(
            amount=Decimal("10.00"),
            currency=Currency.USD,
            description="ClaimProcConflict",
            metadata={},
            idempotency_key="claim-proc-2",
            webhook_url="https://example.com/wh",
        )
        await db_session.commit()

        claimed1 = await repo.claim_processing(payment.id)
        assert claimed1 is not None

        claimed2 = await repo.claim_processing(payment.id)
        assert claimed2 is None

    @pytest.mark.asyncio
    async def test_claim_processing_nonexistent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should return None for a payment that does not exist."""
        repo = PaymentRepository(db_session)
        claimed = await repo.claim_processing(uuid4())
        await db_session.commit()
        assert claimed is None

    @pytest.mark.asyncio
    async def test_claim_finalization_returns_payment(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should claim a PROCESSING payment and finalize to ``succeeded``."""
        repo = PaymentRepository(db_session)
        payment = await repo.add(
            amount=Decimal("10.00"),
            currency=Currency.RUB,
            description="ClaimFinal",
            metadata={},
            idempotency_key="claim-fin-1",
            webhook_url="https://example.com/wh",
        )
        await db_session.commit()

        await repo.claim_processing(payment.id)
        await db_session.commit()

        now = datetime.now(UTC)
        claimed = await repo.claim_finalization(payment.id, PaymentStatus.SUCCEEDED, now)
        await db_session.commit()

        assert claimed is not None
        assert claimed.status == PaymentStatus.SUCCEEDED
        assert claimed.processed_at is not None

    @pytest.mark.asyncio
    async def test_claim_finalization_already_finalized(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should return None when another handler already finalized the payment."""
        repo = PaymentRepository(db_session)
        payment = await repo.add(
            amount=Decimal("10.00"),
            currency=Currency.USD,
            description="ClaimFinConflict",
            metadata={},
            idempotency_key="claim-fin-2",
            webhook_url="https://example.com/wh",
        )
        await db_session.commit()

        await repo.claim_processing(payment.id)
        await db_session.commit()

        now = datetime.now(UTC)
        claimed1 = await repo.claim_finalization(payment.id, PaymentStatus.SUCCEEDED, now)
        assert claimed1 is not None

        claimed2 = await repo.claim_finalization(payment.id, PaymentStatus.FAILED, now)
        assert claimed2 is None

    @pytest.mark.asyncio
    async def test_claim_finalization_nonexistent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should return None for a payment that does not exist."""
        repo = PaymentRepository(db_session)
        now = datetime.now(UTC)
        claimed = await repo.claim_finalization(uuid4(), PaymentStatus.SUCCEEDED, now)
        await db_session.commit()
        assert claimed is None


class TestOutboxRepository:
    """Tests for :class:`OutboxRepository`."""

    @pytest.mark.asyncio
    async def test_add_and_get_unpublished(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should persist and retrieve unpublished outbox events."""
        pay_repo = PaymentRepository(db_session)
        ob_repo = OutboxRepository(db_session)

        payment = await pay_repo.add(
            amount=Decimal("1.00"),
            currency=Currency.USD,
            description="OB",
            metadata={},
            idempotency_key="ob-key-1",
            webhook_url="https://example.com/wh",
        )
        await ob_repo.add(
            aggregate_id=payment.id,
            event_type="payment.created",
            payload={"payment_id": str(payment.id)},
        )
        await db_session.commit()

        messages = await ob_repo.get_unpublished()
        assert len(messages) == 1
        assert messages[0].aggregate_id == payment.id
        assert messages[0].is_published is False

    @pytest.mark.asyncio
    async def test_mark_published(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should mark an outbox event as published."""
        pay_repo = PaymentRepository(db_session)
        ob_repo = OutboxRepository(db_session)

        payment = await pay_repo.add(
            amount=Decimal("1.00"),
            currency=Currency.USD,
            description="OB2",
            metadata={},
            idempotency_key="ob-key-2",
            webhook_url="https://example.com/wh",
        )
        msg = await ob_repo.add(
            aggregate_id=payment.id,
            event_type="payment.created",
            payload={"payment_id": str(payment.id)},
        )
        await db_session.commit()

        now = datetime.now(UTC)
        await ob_repo.mark_published(msg.id, published_at=now)
        await db_session.commit()

        messages = await ob_repo.get_unpublished()
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_get_unpublished_returns_in_order(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should return unpublished events ordered by creation time."""
        pay_repo = PaymentRepository(db_session)
        ob_repo = OutboxRepository(db_session)

        payment = await pay_repo.add(
            amount=Decimal("1.00"),
            currency=Currency.USD,
            description="Multi",
            metadata={},
            idempotency_key="ob-key-3",
            webhook_url="https://example.com/wh",
        )
        for i in range(3):
            await ob_repo.add(
                aggregate_id=payment.id,
                event_type="payment.created",
                payload={"index": i},
            )
        await db_session.commit()

        messages = await ob_repo.get_unpublished()
        assert len(messages) == 3

    @pytest.mark.asyncio
    async def test_get_unpublished_with_limit(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should respect the ``limit`` parameter."""
        pay_repo = PaymentRepository(db_session)
        ob_repo = OutboxRepository(db_session)

        payment = await pay_repo.add(
            amount=Decimal("1.00"),
            currency=Currency.USD,
            description="Limit",
            metadata={},
            idempotency_key="ob-key-4",
            webhook_url="https://example.com/wh",
        )
        for i in range(5):
            await ob_repo.add(
                aggregate_id=payment.id,
                event_type="payment.created",
                payload={"index": i},
            )
        await db_session.commit()

        messages = await ob_repo.get_unpublished(limit=2)
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_get_unpublished_empty(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Should return an empty list when no unpublished events exist."""
        ob_repo = OutboxRepository(db_session)
        messages = await ob_repo.get_unpublished()
        assert messages == []
