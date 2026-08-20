from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from payment_service.consumer.webhook import HttpxWebhookSender
from payment_service.settings import Settings, Webhook


@pytest.fixture()
def webhook_sender() -> HttpxWebhookSender:
    """Return a webhook sender with short timeouts for tests."""
    settings = Settings(webhook=Webhook(timeout=2, max_attempts=3, initial_delay=0.01))
    return HttpxWebhookSender(settings)


class TestHttpxWebhookSender:
    """Tests for :class:`HttpxWebhookSender`."""

    @pytest.mark.asyncio
    async def test_send_success(self, webhook_sender: HttpxWebhookSender) -> None:
        """Should return ``True`` on HTTP 200."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock(return_value=None)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("payment_service.consumer.webhook.httpx.AsyncClient", return_value=mock_client):
            result = await webhook_sender.send(
                "https://example.com/webhook",
                {"payment_id": "123"},
            )

        assert result is True
        mock_client.post.assert_called_once_with(
            "https://example.com/webhook",
            json={"payment_id": "123"},
        )

    @pytest.mark.asyncio
    async def test_send_http_error_retries(
        self,
        webhook_sender: HttpxWebhookSender,
    ) -> None:
        """Should retry on ``HTTPStatusError`` and eventually fail."""
        error_response = MagicMock()
        error_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("POST", "https://example.com/webhook"),
                response=httpx.Response(500),
            ),
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=error_response)

        with patch("payment_service.consumer.webhook.httpx.AsyncClient", return_value=mock_client):
            result = await webhook_sender.send(
                "https://example.com/webhook",
                {"payment_id": "456"},
            )

        assert result is False
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_send_connection_error_retries(
        self,
        webhook_sender: HttpxWebhookSender,
    ) -> None:
        """Should retry on ``ConnectError`` and eventually fail."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with patch("payment_service.consumer.webhook.httpx.AsyncClient", return_value=mock_client):
            result = await webhook_sender.send(
                "https://example.com/webhook",
                {"payment_id": "789"},
            )

        assert result is False
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_send_succeeds_on_second_attempt(
        self,
        webhook_sender: HttpxWebhookSender,
    ) -> None:
        """Should succeed if the second attempt returns 200."""
        error_response = MagicMock()
        error_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("POST", "https://example.com/webhook"),
                response=httpx.Response(503),
            ),
        )
        ok_response = MagicMock()
        ok_response.raise_for_status = MagicMock(return_value=None)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(
            side_effect=[error_response, ok_response],
        )

        with patch("payment_service.consumer.webhook.httpx.AsyncClient", return_value=mock_client):
            result = await webhook_sender.send(
                "https://example.com/webhook",
                {"payment_id": "retry-me"},
            )

        assert result is True
        assert mock_client.post.call_count == 2
