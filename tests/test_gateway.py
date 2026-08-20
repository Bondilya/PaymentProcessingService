import pytest

from payment_service.consumer.gateway import EmulatedPaymentGateway, GatewayResponse
from payment_service.settings import Gateway, Settings


@pytest.fixture()
def gateway() -> EmulatedPaymentGateway:
    """Return a gateway with zero delay and 100 % success."""
    settings = Settings(gateway=Gateway(min_delay=0.0, max_delay=0.0, success_rate=1.0))
    return EmulatedPaymentGateway(settings)


@pytest.fixture()
def failing_gateway_instance() -> EmulatedPaymentGateway:
    """Return a gateway that always fails."""
    settings = Settings(gateway=Gateway(min_delay=0.0, max_delay=0.0, success_rate=0.0))
    return EmulatedPaymentGateway(settings)


class TestEmulatedPaymentGateway:
    """Tests for :class:`EmulatedPaymentGateway`."""

    @pytest.mark.asyncio
    async def test_process_success(self, gateway: EmulatedPaymentGateway) -> None:
        """Gateway should return success when success_rate is 1.0."""
        result = await gateway.process("pay-123", "100.00", "USD")
        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_process_failure(
        self,
        failing_gateway_instance: EmulatedPaymentGateway,
    ) -> None:
        """Gateway should return failure when success_rate is 0.0."""
        result = await failing_gateway_instance.process("pay-456", "50.00", "EUR")
        assert result.success is False
        assert result.error is not None
        assert "pay-456" in result.error

    @pytest.mark.asyncio
    async def test_gateway_response_attributes(self) -> None:
        """``GatewayResponse`` should expose ``success`` and ``error``."""
        ok = GatewayResponse(success=True)
        assert ok.success is True
        assert ok.error is None

        fail = GatewayResponse(success=False, error="Declined")
        assert fail.success is False
        assert fail.error == "Declined"

    @pytest.mark.asyncio
    async def test_process_returns_gateway_response(
        self,
        gateway: EmulatedPaymentGateway,
    ) -> None:
        """``process`` must return a :class:`GatewayResponse` instance."""
        result = await gateway.process("pay-789", "10.00", "RUB")
        assert isinstance(result, GatewayResponse)
