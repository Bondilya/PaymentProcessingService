import pytest
from httpx import AsyncClient


class TestCreatePayment:
    """Tests for ``POST /api/v1/payments``."""

    @pytest.mark.asyncio
    async def test_create_payment_success(self, api_client: AsyncClient) -> None:
        """Should return 202 with payment details."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "100.50",
                "currency": "USD",
                "description": "Test payment",
                "metadata": {"order_id": "ORD-1"},
                "webhook_url": "https://example.com/webhook",
            },
            headers={
                "X-API-Key": "sk-test-key",
                "Idempotency-Key": "api-key-001",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "payment_id" in data
        assert data["status"] == "pending"
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_payment_missing_api_key(self, api_client: AsyncClient) -> None:
        """Should return 401 when API key is missing."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "100.00",
                "currency": "USD",
                "description": "Test",
                "metadata": {},
                "webhook_url": "https://example.com/webhook",
            },
            headers={"Idempotency-Key": "api-key-002"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_payment_wrong_api_key(self, api_client: AsyncClient) -> None:
        """Should return 401 when API key is wrong."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "100.00",
                "currency": "USD",
                "description": "Test",
                "metadata": {},
                "webhook_url": "https://example.com/webhook",
            },
            headers={
                "X-API-Key": "wrong-key",
                "Idempotency-Key": "api-key-003",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_payment_missing_idempotency_key(self, api_client: AsyncClient) -> None:
        """Should return 422 when Idempotency-Key header is missing."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "100.00",
                "currency": "USD",
                "description": "Test",
                "metadata": {},
                "webhook_url": "https://example.com/webhook",
            },
            headers={"X-API-Key": "sk-test-key"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_payment_idempotent(self, api_client: AsyncClient) -> None:
        """Should return the same payment for duplicate idempotency key."""
        payload = {
            "amount": "50.00",
            "currency": "EUR",
            "description": "Idempotent test",
            "metadata": {"k": "v"},
            "webhook_url": "https://example.com/webhook",
        }
        headers = {
            "X-API-Key": "sk-test-key",
            "Idempotency-Key": "idem-api-001",
        }

        first = await api_client.post("/api/v1/payments", json=payload, headers=headers)
        assert first.status_code == 202

        second = await api_client.post("/api/v1/payments", json=payload, headers=headers)
        assert second.status_code == 202
        assert first.json()["payment_id"] == second.json()["payment_id"]

    @pytest.mark.asyncio
    async def test_create_payment_invalid_amount_zero(self, api_client: AsyncClient) -> None:
        """Should return 422 for zero amount."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "0",
                "currency": "USD",
                "description": "Zero",
                "metadata": {},
                "webhook_url": "https://example.com/webhook",
            },
            headers={
                "X-API-Key": "sk-test-key",
                "Idempotency-Key": "api-zero",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_payment_invalid_amount_negative(self, api_client: AsyncClient) -> None:
        """Should return 422 for negative amount."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "-10.00",
                "currency": "USD",
                "description": "Negative",
                "metadata": {},
                "webhook_url": "https://example.com/webhook",
            },
            headers={
                "X-API-Key": "sk-test-key",
                "Idempotency-Key": "api-neg",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_payment_invalid_currency(self, api_client: AsyncClient) -> None:
        """Should return 422 for unsupported currency."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "10.00",
                "currency": "GBP",
                "description": "Bad currency",
                "metadata": {},
                "webhook_url": "https://example.com/webhook",
            },
            headers={
                "X-API-Key": "sk-test-key",
                "Idempotency-Key": "api-gbp",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_payment_empty_description(self, api_client: AsyncClient) -> None:
        """Should return 422 for empty description."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "10.00",
                "currency": "USD",
                "description": "",
                "metadata": {},
                "webhook_url": "https://example.com/webhook",
            },
            headers={
                "X-API-Key": "sk-test-key",
                "Idempotency-Key": "api-empty-desc",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_payment_missing_webhook_url(self, api_client: AsyncClient) -> None:
        """Should return 422 when webhook_url is missing."""
        response = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "10.00",
                "currency": "USD",
                "description": "No webhook",
                "metadata": {},
            },
            headers={
                "X-API-Key": "sk-test-key",
                "Idempotency-Key": "api-no-wh",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_payment_all_currencies(self, api_client: AsyncClient) -> None:
        """Should accept all supported currencies."""
        for i, currency in enumerate(["RUB", "USD", "EUR"]):
            response = await api_client.post(
                "/api/v1/payments",
                json={
                    "amount": "10.00",
                    "currency": currency,
                    "description": f"Currency {currency}",
                    "metadata": {},
                    "webhook_url": "https://example.com/webhook",
                },
                headers={
                    "X-API-Key": "sk-test-key",
                    "Idempotency-Key": f"api-currency-{i}",
                },
            )
            assert response.status_code == 202
            assert response.json()["status"] == "pending"


class TestGetPayment:
    """Tests for ``GET /api/v1/payments/{payment_id}``."""

    @pytest.mark.asyncio
    async def test_get_payment_success(self, api_client: AsyncClient) -> None:
        """Should return payment details."""
        create = await api_client.post(
            "/api/v1/payments",
            json={
                "amount": "200.00",
                "currency": "USD",
                "description": "Get test",
                "metadata": {"order": "123"},
                "webhook_url": "https://example.com/webhook",
            },
            headers={
                "X-API-Key": "sk-test-key",
                "Idempotency-Key": "get-key-001",
            },
        )
        payment_id = create.json()["payment_id"]

        response = await api_client.get(
            f"/api/v1/payments/{payment_id}",
            headers={"X-API-Key": "sk-test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["payment_id"] == payment_id
        assert data["amount"] == "200.0000"
        assert data["currency"] == "USD"
        assert data["status"] == "pending"
        assert data["description"] == "Get test"
        assert data["metadata"] == {"order": "123"}
        assert data["webhook_url"] == "https://example.com/webhook"
        assert data["processed_at"] is None

    @pytest.mark.asyncio
    async def test_get_payment_not_found(self, api_client: AsyncClient) -> None:
        """Should return 404 for non-existent payment."""
        response = await api_client.get(
            "/api/v1/payments/00000000-0000-0000-0000-000000000000",
            headers={"X-API-Key": "sk-test-key"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_payment_missing_api_key(self, api_client: AsyncClient) -> None:
        """Should return 401 when API key is missing."""
        response = await api_client.get(
            "/api/v1/payments/00000000-0000-0000-0000-000000000000",
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_payment_invalid_uuid(self, api_client: AsyncClient) -> None:
        """Should return 422 for invalid UUID format."""
        response = await api_client.get(
            "/api/v1/payments/not-a-uuid",
            headers={"X-API-Key": "sk-test-key"},
        )
        assert response.status_code == 422
