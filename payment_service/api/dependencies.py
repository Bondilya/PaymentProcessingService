from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, Any]:
    async with request.app.state.session_factory() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_session)]


async def verify_api_key(
    request: Request,
    *,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Validate the ``X-API-Key`` header against the configured key.

    Args:
        request: Request instance.
        x_api_key: The value of the ``X-API-Key`` header.

    Raises:
        HTTPException: 401 if the header is missing or does not match.
    """
    if x_api_key is None or x_api_key != request.app.state.settings.api.key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key
