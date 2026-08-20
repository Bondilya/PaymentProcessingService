from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from payment_service.api.dependencies import (
    DBSession,
    verify_api_key,
)
from payment_service.api.schemas import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentResponse,
)
from payment_service.api.v1.service import get_payment_service
from payment_service.repositories.payment import PaymentRepository

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PaymentCreateResponse,
    summary="Create a payment",
    description="Create a new payment for asynchronous processing. "
    "Uses the `Idempotency-Key` header to prevent duplicate submissions.",
)
async def create_payment(
    body: PaymentCreateRequest,
    session: DBSession,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
    ),
    _api_key: str = Depends(verify_api_key),
) -> PaymentCreateResponse:
    """Accept a payment request and enqueue it for processing."""
    service = get_payment_service(session)

    payment = await service.create_payment(
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        metadata=body.metadata,
        idempotency_key=idempotency_key,
        webhook_url=str(body.webhook_url),
    )
    return PaymentCreateResponse(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details",
    description="Retrieve detailed information about a specific payment.",
)
async def get_payment(
    payment_id: UUID,
    session: DBSession,
    _api_key: str = Depends(verify_api_key),
) -> PaymentResponse:
    """Return the payment with the given ID."""

    repo = PaymentRepository(session)
    payment = await repo.get_by_id(payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment {payment_id} not found",
        )
    return PaymentResponse(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.metadata,
        status=payment.status,
        idempotency_key=payment.idempotency_key,
        webhook_url=payment.webhook_url,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )
