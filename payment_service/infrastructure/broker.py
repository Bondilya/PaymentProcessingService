from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue

EXCHANGE_NAME = "payments.exchange"
QUEUE_NAME = "payments.new"
DLQ_QUEUE_NAME = "payments.new.dlq"
ROUTING_KEY = "payment.created"
DLQ_ROUTING_KEY = "payment.dead"

payment_exchange = RabbitExchange(name=EXCHANGE_NAME, durable=True)

payment_queue = RabbitQueue(
    name=QUEUE_NAME,
    durable=True,
    routing_key=ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": EXCHANGE_NAME,
        "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
    },
)

dlq_queue = RabbitQueue(
    name=DLQ_QUEUE_NAME,
    durable=True,
    routing_key=DLQ_ROUTING_KEY,
)


def create_broker(url: str) -> RabbitBroker:
    """Create a :class:`RabbitBroker` connected to *url*."""
    return RabbitBroker(url)
