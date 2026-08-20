import logging
from collections.abc import Awaitable, Callable
from typing import Any

from faststream import FastStream
from faststream.middlewares.acknowledgement.config import AckPolicy
from faststream.rabbit import RabbitBroker
from httpx import HTTPStatusError
from sqlalchemy.exc import OperationalError
from tenacity import AsyncRetrying, TryAgain, retry_if_exception_type, stop_after_attempt, wait_exponential

from payment_service.consumer.payment_processor import PaymentProcessor
from payment_service.infrastructure.broker import (
    dlq_queue,
    payment_exchange,
    payment_queue,
)
from payment_service.settings import Settings

logger = logging.getLogger(__name__)


RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError, OperationalError, HTTPStatusError)

class ProcessingError(Exception):
    """Raised when payment processing fails after all retries."""


def create_consumer(
    settings: Settings,
    processor: PaymentProcessor,
) -> FastStream:
    """Build and wire the FastStream consumer application.

    Registers subscribers for ``payments.new`` (with retry-on-error) and
    ``payments.new.dlq`` queues.

    Args:
        settings: Application settings (broker URL, consumer config, etc.).
        processor: :class:`PaymentProcessor` instance that handles individual
            payment events.

    Returns:
        Configured :class:`FastStream` application.
    """

    broker = RabbitBroker(settings.broker.url)
    app = FastStream(broker)

    handler = make_payment_handler(processor, settings)

    broker.subscriber(
        queue=payment_queue,
        exchange=payment_exchange,
        ack_policy=AckPolicy.REJECT_ON_ERROR,
    )(handler)

    broker.subscriber(
        queue=dlq_queue,
        exchange=payment_exchange,
    )(handle_dead_letter)

    return app


def make_payment_handler(
    processor: PaymentProcessor,
    settings: Settings,
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    """Return an async handler for the ``payment.created`` event.

    The returned coroutine retries ``processor.process()``.

    Args:
        processor: The :class:`PaymentProcessor` to invoke.
        settings: Application settings controlling retry behavior.

    Returns:
        An async function accepting a ``message: dict[str, Any]`` payload
        and returning ``None``.
    """

    async def handle_payment_created(message: dict[str, Any]) -> None:
        """Handle a ``payment.created`` event with retry.

        Args:
            message: Event payload containing ``payment_id``.
        """
        if "payment_id" not in message:
            logger.error("Missing payment_id in message")
            raise ProcessingError("Invalid message payload")

        payment_id = message["payment_id"]
        logger.info("Received payment.created event for %s", payment_id)

        retrying = AsyncRetrying(
            stop=stop_after_attempt(settings.consumer.max_attempts),
            wait=wait_exponential(
                multiplier=settings.consumer.initial_delay,
                min=settings.consumer.initial_delay,
            ),
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        )

        last_exc: Exception | None = None
        async for attempt in retrying:
            with attempt:
                try:
                    await processor.process(payment_id)
                    logger.info(
                        "Payment %s processed successfully (attempt %d)",
                        payment_id,
                        attempt.retry_state.attempt_number,
                    )
                except RETRYABLE_EXCEPTIONS as exc:
                    last_exc = exc
                    raise TryAgain() from exc
                except Exception as exc:
                    last_exc = exc
                    break

        if last_exc is not None:
            raise ProcessingError(
                f"Payment {payment_id} failed after all retries"
            ) from last_exc

    return handle_payment_created


async def handle_dead_letter(message: dict[str, Any]) -> None:
    """Log the content of a dead-lettered message.

    Args:
        message: The message payload that ended up in the DLQ.
    """
    logger.error("Dead-letter message received: %s", message)
