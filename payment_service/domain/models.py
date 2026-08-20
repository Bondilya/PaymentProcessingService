from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from payment_service.domain.enums import Currency, PaymentStatus


class Payment:
    """Aggregate root representing a payment request.

    This is a plain domain object — only about the business rules of a payment.
    """

    def __init__(
        self,
        *,
        id_: UUID,
        amount: Decimal,
        currency: Currency,
        description: str,
        metadata: dict[str, Any],
        status: PaymentStatus,
        idempotency_key: str,
        webhook_url: str,
        created_at: datetime,
        processed_at: datetime | None = None,
    ) -> None:
        self.id = id_
        self.amount = amount
        self.currency = currency
        self.description = description
        self.metadata = metadata
        self.status = status
        self.idempotency_key = idempotency_key
        self.webhook_url = webhook_url
        self.created_at = created_at
        self.processed_at = processed_at

    def mark_succeeded(self, *, processed_at: datetime) -> None:
        """Transition the payment to ``succeeded``."""
        self.status = PaymentStatus.SUCCEEDED
        self.processed_at = processed_at

    def mark_failed(self, *, processed_at: datetime) -> None:
        """Transition the payment to ``failed``."""
        self.status = PaymentStatus.FAILED
        self.processed_at = processed_at


class OutboxMessage:
    """Outbox event awaiting publication to the message broker."""

    def __init__(
        self,
        *,
        id_: int,
        aggregate_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        created_at: datetime,
        published_at: datetime | None = None,
    ) -> None:
        self.id = id_
        self.aggregate_id = aggregate_id
        self.event_type = event_type
        self.payload = payload
        self.created_at = created_at
        self.published_at = published_at

    @property
    def is_published(self) -> bool:
        """Return ``True`` when the message has been published."""
        return self.published_at is not None
