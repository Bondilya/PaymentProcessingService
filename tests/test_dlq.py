from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.consumer.main import ProcessingError, create_consumer, make_payment_handler
from payment_service.consumer.payment_processor import PaymentProcessor
from payment_service.domain.enums import Currency
from payment_service.repositories.payment import PaymentRepository


class TestDLQFlow:
    """Tests for DLQ routing when processing fails after all retries."""

    @pytest.mark.asyncio
    async def test_handle_payment_created_raises_processing_error_on_gateway_error(
        self,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
        test_settings: Any,
    ) -> None:
        """When the gateway raises an exception, handle_payment_created must
        propagate it so that FastStream + REJECT_ON_ERROR routes the message
        to the DLQ."""
        from unittest.mock import AsyncMock, MagicMock

        from payment_service.consumer.gateway import IPaymentGateway

        mock_gateway = MagicMock(spec=IPaymentGateway)
        mock_gateway.process = AsyncMock(side_effect=RuntimeError("Gateway unreachable"))

        mock_webhook_sender = MagicMock()
        mock_webhook_sender.send = AsyncMock(return_value=True)

        processor = PaymentProcessor(
            session_factory=sqlite_session_factory,
            gateway=mock_gateway,
            webhook_sender=mock_webhook_sender,
        )

        create_consumer(
            settings=test_settings,
            processor=processor,
        )

        async with sqlite_session_factory() as session:
            repo = PaymentRepository(session)
            payment = await repo.add(
                amount=100.00,
                currency=Currency.USD,
                description="DLQ gateway error",
                metadata={},
                idempotency_key="dlq-gw-error",
                webhook_url="https://example.com/webhook",
            )
            payment_id = str(payment.id)
            await session.commit()

        handler = make_payment_handler(processor, test_settings)

        with pytest.raises(ProcessingError):
            await handler({"payment_id": payment_id})

    @pytest.mark.asyncio
    async def test_handle_payment_created_raises_on_missing_payment_id(
        self,
        test_settings: Any,
        mock_gateway: MagicMock,
        mock_webhook_sender: MagicMock,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """When message lacks payment_id, ProcessingError is raised immediately."""
        from payment_service.consumer.main import make_payment_handler

        processor = PaymentProcessor(
            session_factory=sqlite_session_factory,
            gateway=mock_gateway,
            webhook_sender=mock_webhook_sender,
        )

        handler = make_payment_handler(processor, test_settings)

        message: dict[str, Any] = {"some_other_field": "value"}

        with pytest.raises(ProcessingError, match="Invalid message payload"):
            await handler(message)

    @pytest.mark.asyncio
    async def test_handle_payment_created_succeeds_does_not_raise(
        self,
        sqlite_session_factory: async_sessionmaker[AsyncSession],
        mock_gateway: MagicMock,
        mock_webhook_sender: MagicMock,
        test_settings: Any,
    ) -> None:
        """When processing succeeds, no exception is raised — message is ACK'd."""
        from payment_service.consumer.main import make_payment_handler

        processor = PaymentProcessor(
            session_factory=sqlite_session_factory,
            gateway=mock_gateway,
            webhook_sender=mock_webhook_sender,
        )

        handler = make_payment_handler(processor, test_settings)

        async with sqlite_session_factory() as session:
            repo = PaymentRepository(session)
            payment = await repo.add(
                amount=100.00,
                currency=Currency.USD,
                description="DLQ success",
                metadata={},
                idempotency_key="dlq-success",
                webhook_url="https://example.com/webhook",
            )
            payment_id = str(payment.id)
            await session.commit()

        await handler({"payment_id": payment_id})

        mock_gateway.process.assert_called_once()
