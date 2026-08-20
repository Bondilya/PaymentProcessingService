import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from payment_service.api.v1.main_router import api_router
from payment_service.infrastructure.database import create_engine, create_session_factory
from payment_service.logging_config import setup_logging
from payment_service.settings import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown of the outbox publisher and broker.

    Args:
        app_: The FastAPI application instance.
    """
    from payment_service.api.outbox_publisher import OutboxPublisher
    from payment_service.infrastructure.broker import create_broker, dlq_queue, payment_exchange, payment_queue

    app_.state.settings = Settings()
    setup_logging()

    engine = create_engine(app_.state.settings.db)
    app_.state.session_factory = create_session_factory(engine)

    broker = create_broker(app_.state.settings.broker.url)
    await broker.connect()
    logger.info("RabbitMQ broker connected")

    await broker.declare_exchange(payment_exchange)
    await broker.declare_queue(payment_queue)
    await broker.declare_queue(dlq_queue)

    publisher = OutboxPublisher(
        session_factory=app_.state.session_factory,
        broker=broker,
        settings=app_.state.settings.outbox,
    )
    task = asyncio.create_task(publisher.start())

    app_.state.broker = broker
    app_.state.publisher = publisher
    app_.state.publisher_task = task

    yield

    await publisher.stop()

    shutdown_timeout = app_.state.settings.outbox.shutdown_timeout
    try:
        await asyncio.wait_for(
            asyncio.shield(task),
            timeout=shutdown_timeout,
        )
    except TimeoutError:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.warning("Outbox publisher did not stop within %.1fs — force-killed", shutdown_timeout)
    except asyncio.CancelledError:
        pass
    await broker.stop()
    logger.info("RabbitMQ broker closed")
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app_ = FastAPI(
        title="Payment Processing Service",
        version="1.0.0",
        description="Asynchronous payment processing microservice",
        lifespan=lifespan,
    )
    app_.include_router(api_router)
    return app_


app = create_app()
