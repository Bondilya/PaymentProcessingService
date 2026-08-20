import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.consumer.gateway import IPaymentGateway
from payment_service.consumer.webhook import IWebhookSender
from payment_service.domain.enums import PaymentStatus
from payment_service.domain.models import Payment
from payment_service.repositories.payment import PaymentRepository

logger = logging.getLogger(__name__)


class PaymentProcessor:
    """Concrete processor that orchestrates gateway → DB → webhook."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: IPaymentGateway,
        webhook_sender: IWebhookSender,
    ) -> None:
        self._session_factory = session_factory
        self._gateway = gateway
        self._webhook_sender = webhook_sender

    async def process(self, payment_id: str) -> None:
        """Process a payment: charge, update status, send webhook.

        Args:
            payment_id: UUID string of the payment to process.
        """
        uuid = UUID(payment_id)

        async with self._session_factory() as session:
            payment_repo = PaymentRepository(session)
            payment = await payment_repo.claim_processing(uuid)
            if payment is None:
                logger.debug("Payment %s already claimed or not found — skipping", payment_id)
                return

            await session.commit()

        result = await self._gateway.process(
            payment_id=str(payment.id),
            amount=str(payment.amount),
            currency=payment.currency.value,
        )

        now = datetime.now(UTC)
        async with self._session_factory() as session:
            payment_repo = PaymentRepository(session)
            if result.success:
                payment = await payment_repo.claim_finalization(payment.id, PaymentStatus.SUCCEEDED, now)
            else:
                payment = await payment_repo.claim_finalization(payment.id, PaymentStatus.FAILED, now)

            if payment is None:
                logger.debug("Payment %s already finalized by another handler — skipping", payment_id)
                return

            await session.commit()

        await self._send_webhook(payment)

    async def _send_webhook(self, payment: Payment) -> None:
        """Deliver the webhook notification for *payment*."""
        payload: dict[str, object] = {
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "amount": str(payment.amount),
            "currency": payment.currency.value,
            "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
        }
        delivered = await self._webhook_sender.send(payment.webhook_url, payload)
        if not delivered:
            logger.error(
                "Webhook delivery failed for payment %s after all retries",
                payment.id,
            )
