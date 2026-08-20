from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from payment_service.consumer.gateway import GatewayResponse, IPaymentGateway
from payment_service.consumer.webhook import IWebhookSender
from payment_service.domain.enums import Currency, PaymentStatus
from payment_service.domain.models import Payment
from payment_service.infrastructure.models import Base
from payment_service.settings import Settings

# ---------------------------------------------------------------------------
# Settings override
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_settings() -> Settings:
    """Return settings tuned for tests (values loaded from ``.env.test``)."""
    _test_env = Path(__file__).resolve().parent.parent / ".env.test"

    return Settings(_env_file=_test_env)


# ---------------------------------------------------------------------------
# SQLite in-memory database (unit tests)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def sqlite_engine() -> AsyncIterator[Any]:
    """Create an in-memory SQLite async engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def sqlite_session_factory(sqlite_engine: Any) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the in-memory SQLite engine."""
    return async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture()
async def db_session(sqlite_session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Yield a clean database session for each test."""
    async with sqlite_session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Domain entity factory
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_payment() -> Payment:
    """Return a sample pending payment entity."""
    return Payment(
        id_=uuid4(),
        amount=Decimal("100.50"),
        currency=Currency.USD,
        description="Test payment",
        metadata={"order_id": "ORD-123"},
        status=PaymentStatus.PENDING,
        idempotency_key="idem-key-001",
        webhook_url="https://example.com/webhook",
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Mock collaborators
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_gateway() -> MagicMock:
    """Return a mock :class:`IPaymentGateway`."""
    gateway = MagicMock(spec=IPaymentGateway)
    gateway.process = AsyncMock(return_value=GatewayResponse(success=True))
    return gateway


@pytest.fixture()
def mock_webhook_sender() -> MagicMock:
    """Return a mock :class:`IWebhookSender`."""
    sender = MagicMock(spec=IWebhookSender)
    sender.send = AsyncMock(return_value=True)
    return sender


@pytest.fixture()
def failing_gateway() -> MagicMock:
    """Return a mock gateway that always fails."""
    gateway = MagicMock(spec=IPaymentGateway)
    gateway.process = AsyncMock(
        return_value=GatewayResponse(success=False, error="Declined"),
    )
    return gateway


@pytest.fixture()
def failing_webhook_sender() -> MagicMock:
    """Return a mock webhook sender that always fails."""
    sender = MagicMock(spec=IWebhookSender)
    sender.send = AsyncMock(return_value=False)
    return sender


# ---------------------------------------------------------------------------
# HTTP test client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def api_client(
    test_settings: "Settings",
    mock_gateway: MagicMock,
    mock_webhook_sender: MagicMock,
    sqlite_engine: Any,
    sqlite_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """Return an ``httpx.AsyncClient`` wired to the FastAPI app.

    The app uses SQLite in-memory and mock collaborators so that tests
    run without external services.
    """

    from payment_service.api.main import create_app

    app = create_app()
    app.state.settings = Settings(_env_file=".env.test")
    app.state.session_factory = sqlite_session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client._app = app  # type: ignore[attr-defined]
        yield client
