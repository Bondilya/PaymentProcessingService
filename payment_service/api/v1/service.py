import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain.enums import Currency
from payment_service.domain.models import Payment
from payment_service.infrastructure.database import SqlAlchemyUnitOfWork
from payment_service.repositories.outbox import OutboxRepository
from payment_service.repositories.payment import PaymentRepository

logger = logging.getLogger(__name__)


class PaymentService:
    """Application service for creating payments.

    Depends on a unit-of-work (which provides the transactional session)
    rather than on concrete repositories, following DIP.
    """

    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: Currency,
        description: str,
        metadata: dict[str, object],
        idempotency_key: str,
        webhook_url: str,
    ) -> Payment:
        """Create a payment and an outbox event atomically.

        If a payment with the same *idempotency_key* already exists, the
        existing payment is returned (idempotency guarantee).

        Returns:
            The created or existing :class:`Payment`.
        """
        async with self._uow as uow:
            payment_repo = PaymentRepository(uow.session)
            outbox_repo = OutboxRepository(uow.session)

            existing = await payment_repo.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                logger.info(
                    "Idempotent replay for key=%s → payment %s",
                    idempotency_key,
                    existing.id,
                )
                return existing

            payment = await payment_repo.add(
                amount=amount,
                currency=currency,
                description=description,
                metadata=metadata,
                idempotency_key=idempotency_key,
                webhook_url=webhook_url,
            )

            await outbox_repo.add(
                aggregate_id=payment.id,
                event_type="payment.created",
                payload={
                    "payment_id": str(payment.id),
                    "amount": str(payment.amount),
                    "currency": payment.currency.value,
                },
            )

            logger.info("Created payment %s (key=%s)", payment.id, idempotency_key)
            return payment


def get_payment_service(session: AsyncSession) -> PaymentService:
    """Return a :class:`PaymentService` using the session."""
    uow = SqlAlchemyUnitOfWork(session)
    return PaymentService(uow)
