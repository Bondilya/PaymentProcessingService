import asyncio
import random
from typing import Protocol

from payment_service.settings import Settings


class GatewayResponse:
    """Concrete gateway response container."""

    def __init__(self, *, success: bool, error: str | None = None) -> None:
        self.success = success
        self.error = error


class IPaymentGateway(Protocol):
    """Abstract interface for processing payments externally."""

    async def process(
        self,
        payment_id: str,
        amount: str,
        currency: str,
    ) -> GatewayResponse:
        """Attempt to charge the payment and return the result."""
        ...


class EmulatedPaymentGateway:
    """Simulated payment gateway with configurable delay and success rate."""

    def __init__(self, settings: Settings) -> None:
        self._min_delay = settings.gateway.min_delay
        self._max_delay = settings.gateway.max_delay
        self._success_rate = settings.gateway.success_rate

    async def process(
        self,
        payment_id: str,
        amount: str,
        currency: str,
    ) -> GatewayResponse:
        """Sleep for a random duration, then succeed or fail probabilistically."""
        delay = random.uniform(self._min_delay, self._max_delay)
        await asyncio.sleep(delay)

        if random.random() < self._success_rate:
            return GatewayResponse(success=True)

        return GatewayResponse(
            success=False,
            error=f"Gateway declined payment {payment_id} ({amount} {currency})",
        )
