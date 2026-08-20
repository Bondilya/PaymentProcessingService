import asyncio
import logging

from payment_service.consumer.gateway import EmulatedPaymentGateway
from payment_service.consumer.main import create_consumer
from payment_service.consumer.payment_processor import PaymentProcessor
from payment_service.consumer.webhook import HttpxWebhookSender
from payment_service.infrastructure.database import create_engine, create_session_factory
from payment_service.logging_config import setup_logging
from payment_service.settings import Settings

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    settings = Settings()

    session_factory = create_session_factory(create_engine(settings.db))
    gateway = EmulatedPaymentGateway(settings)
    webhook_sender = HttpxWebhookSender(settings)
    processor = PaymentProcessor(
        session_factory=session_factory,
        gateway=gateway,
        webhook_sender=webhook_sender,
    )

    app = create_consumer(
        settings=settings,
        processor=processor,
    )
    setup_logging()
    logger.info("Starting consumer on %s", settings.broker.url)
    asyncio.run(app.run())
