import logging
from typing import Protocol

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from payment_service.settings import Settings

logger = logging.getLogger(__name__)


class IWebhookSender(Protocol):
    """Abstract interface for delivering webhook notifications."""

    async def send(
        self,
        url: str,
        payload: dict[str, object],
    ) -> bool:
        """Deliver *payload* to *url*.  Return ``True`` on success."""
        ...


class HttpxWebhookSender:
    """HTTP-based webhook sender using ``httpx.AsyncClient``."""

    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.webhook.timeout
        self._max_attempts = settings.webhook.max_attempts
        self._initial_delay = settings.webhook.initial_delay

    async def send(
        self,
        url: str,
        payload: dict[str, object],
    ) -> bool:
        """POST *payload* to *url* with retry.

        Returns:
            ``True`` if the webhook was delivered (HTTP 2xx),
            ``False`` if all attempts failed.
        """
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=self._initial_delay, min=self._initial_delay),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=False,
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async for attempt in retrying:
                    with attempt:
                        logger.debug(
                            "Sending webhook to %s (payment_id=%s, status=%s, attempt=%d)",
                            url,
                            payload.get("payment_id"),
                            payload.get("status"),
                            attempt.retry_state.attempt_number,
                        )
                        response = await client.post(url, json=payload)
                        response.raise_for_status()
                        logger.debug(
                            "Webhook delivered to %s (attempt %d)",
                            url,
                            attempt.retry_state.attempt_number,
                        )
                        return True
        except RetryError:
            logger.warning(
                "Webhook delivery to %s failed after all retries (payment_id=%s)",
                url,
                payload.get("payment_id"),
            )
            return False

        return False
