from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from payment_service.settings import DB


def create_engine(settings: DB) -> AsyncEngine:
    return create_async_engine(
        settings.url,
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.pool_max_size,
        max_overflow=settings.pool_max_overflow,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


class SqlAlchemyUnitOfWork:
    """Concrete UoW wrapping an :class:`AsyncSession` instance."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            await self._session.rollback()
        else:
            await self._session.commit()
        await self._session.close()

    @property
    def session(self) -> AsyncSession:
        """Return the active session."""
        return self._session
