from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from payment_service.domain.enums import Currency, PaymentStatus


class PaymentCreateRequest(BaseModel):
    """Request body for ``POST /api/v1/payments``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: Decimal = Field(..., gt=0, description="Payment amount (must be positive)")
    currency: Currency = Field(..., description="Currency code")
    description: str = Field(..., min_length=1, max_length=1000, description="Payment description")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata",
    )
    webhook_url: HttpUrl = Field(..., description="URL to receive the result webhook")


class PaymentCreateResponse(BaseModel):
    """Response body for ``POST /api/v1/payments`` (202 Accepted)."""

    payment_id: UUID
    status: PaymentStatus
    created_at: datetime


class PaymentResponse(BaseModel):
    """Detailed payment representation for ``GET /api/v1/payments/{id}``."""

    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None = None
