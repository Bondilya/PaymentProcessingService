# Payment Processing Service

Асинхронный микросервис для обработки платежей с использованием Outbox Pattern, idempotency keys и retry-логики.

## Стек

| Компонент | Технология |
|-----------|---|
| API       | FastAPI + Pydantic v2 |
| ORM       | SQLAlchemy 2.0 (async) |
| БД        | PostgreSQL |
| Брокер    | RabbitMQ (FastStream) |
| Миграции  | Alembic |
| Линтеры   | Ruff + mypy |
| Тесты     | pytest + pytest-asyncio |

## Архитектура

```
payment_service/
├── api/                    # FastAPI layer
│   ├── main.py             # App factory + lifespan (broker + outbox)
│   ├── start.py            # Docker entry: uvicorn "main:app"
│   ├── dependencies.py     # DI deps (session, API key auth)
│   ├── schemas.py          # Pydantic v2 response/request models
│   ├── outbox_publisher.py # Background outbox → RabbitMQ relay
│   └── v1/
│       ├── main_router.py  # Router mount at /api/v1
│       ├── routers.py      # Payment CRUD endpoints
│       └── service.py      # PaymentService (create + idempotency + outbox write)
├── consumer/               # FastStream subscriber
│   ├── main.py             # Subscriber: handle_payment_created + create_consumer()
│   ├── start.py            # Docker entry: asyncio.run(app.run())
│   ├── payment_processor.py # Gateway call + status update
│   ├── gateway.py          # IPaymentGateway / EmulatedPaymentGateway
│   └── webhook.py          # IWebhookSender / HttpxWebhookSender (tenacity retry)
├── domain/
│   ├── models.py           # Plain entities: Payment, OutboxMessage
│   └── enums.py            # Currency, PaymentStatus
├── infrastructure/
│   ├── models.py           # SQLAlchemy ORM: PaymentModel, OutboxModel
│   ├── database.py         # asyncpg engine + session factory
│   └── broker.py           # RabbitMQ exchange/queue/DLQ declaration
├── repositories/           # SQLAlchemy repository implementations
│   ├── payment.py
│   └── outbox.py
└── settings.py             # pydantic-settings (DB, Broker, Outbox, Gateway, Webhook, Consumer, API)
```

### Ключевые паттерны

- **Outbox Pattern** — событие `payment.created` записывается в таблицу `outbox` в той же транзакции, что и платёж. `OutboxPublisher` (фоновая задача в lifespan) периодически опрашивает `outbox WHERE published_at IS NULL` и публикует события в RabbitMQ.
- **Idempotency** — заголовок `Idempotency-Key` предотвращает дублирование платежей при повторных запросах.
- **Retry + DLQ** — потребитель повторяет обработку с экспоненциальной задержкой (tenacity). Упавшие сообщения направляются в DLQ (`payments.new.dlq`) через `AckPolicy.REJECT_ON_ERROR`.
- **Logging** — логгер настраивается в `payment_service.logging_config` и используется как API, так и consumer.

## Быстрый старт

```bash
# Активация виртуального окружения
# Windows:  .venv\Scripts\activate
# POSIX:    source .venv/bin/activate

# Запуск PostgreSQL + RabbitMQ
docker compose up -d

# Применение миграций
python -m alembic upgrade head

# Запуск API (dev-сервер)
uvicorn payment_service.api.main:app --reload

# Запуск consumer (отдельный терминал)
python -m payment_service.consumer.main
```

### Docker

Сервисы API и consumer также запускаются через `docker compose up` (см. `docker-compose.yml`):

- `api` — собирает образ из `Dockerfile`, применяет миграции и запускает uvicorn.
- `consumer` — применяет миграции и запускает consumer через `payment_service.consumer.start`.

## Тесты

Все unit-тесты используют **SQLite in-memory** через `aiosqlite` и не требуют PostgreSQL или RabbitMQ.

```bash
# Все тесты
pytest tests/ -v

# Только не-integration тесты
pytest tests/ -v -m "not integration"

# Покрытие
pytest tests/ -v --cov=payment_service --cov-report=html
```

## Linting и Type Checking

```bash
# Ruff (код-стайл + форматирование)
ruff check .
ruff format .

# Mypy (strict mode)
mypy payment_service/
```

## Запуск

### Предварительные требования

- Python 3.12+
- Docker + Docker Compose
- Виртуальное окружение (рекомендуется)

### Настройка окружения

```bash
cp .env.example .env
# Отредактируйте .env при необходимости
```

Для тестов используется `.env.test` — он автоматически подхватывается через `Settings(_env_file=".env.test")` в `conftest.py`.

### API

```bash
uvicorn payment_service.api.main:app --reload
```

Docker-вход: `python -m payment_service.api.start` (хост/порт из настроек).

### Consumer

```bash
python -m payment_service.consumer.main
```

Docker-вход: `python -m payment_service.consumer.start`.

## API

### Создание платежа

```http
POST /api/v1/payments
Idempotency-Key: unique-key-123
X-API-Key: sk-test-key

{
  "amount": 100.50,
  "currency": "USD",
  "description": "Order #123",
  "metadata": {"order_id": "123"},
  "webhook_url": "https://example.com/webhook"
}
```

**Ответ 202 Accepted:**
```json
{
  "payment_id": "uuid",
  "status": "pending",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Получение платежа

```http
GET /api/v1/payments/{payment_id}
X-API-Key: sk-test-key
```

**Ответ 200:**
```json
{
  "payment_id": "uuid",
  "amount": "100.5000",
  "currency": "USD",
  "description": "Order #123",
  "metadata": {"order_id": "123"},
  "status": "pending",
  "idempotency_key": "unique-key-123",
  "webhook_url": "https://example.com/webhook",
  "created_at": "2025-01-01T00:00:00Z",
  "processed_at": null
}
```

### Получение документации

```bash
# Swagger UI
http://localhost:8000/docs

# ReDoc
http://localhost:8000/redoc
```

## Тестовое покрытие

**~50 тестов** покрывают:

| Слой | Описание |
|---|---|
| API | Создание, получение, валидация, idempotency, API key auth |
| PaymentService | Создание, idempotency, outbox write, metadata |
| Consumer | Gateway вызов, статус, webhook, обработка ошибок |
| Repositories | CRUD, outbox query/publish, claim-механизм |
| Gateway | Success / failure response |
| Webhook | Retry логика, HTTP errors, connection errors |
| DLQ | Routing dead-lettered сообщений |

## Структура базы данных

```sql
payments
├── id (UUID, PK)
├── amount (NUMERIC)
├── currency (VARCHAR(3))
├── description (TEXT)
├── metadata (JSONB)
├── status (VARCHAR(20))
├── idempotency_key (VARCHAR(255), UNIQUE)
├── webhook_url (TEXT)
├── created_at (TIMESTAMP)
└── processed_at (TIMESTAMP)

outbox_messages
├── id (INT, PK)
├── aggregate_id (UUID, FK → payments.id)
├── event_type (VARCHAR(50))
├── payload (JSONB)
├── created_at (TIMESTAMP)
└── published_at (TIMESTAMP)
```

## Настройки

Settings через `pydantic-settings`, переменные из `.env`. Вложенные модели используют `__` разделитель (например, `DB__NAME`, `BROKER__PORT`).

| Раздел | Переменные |
|---|---|
| DB | `DB__NAME`, `DB__USER`, `DB__PASSWORD`, `DB__HOST`, `DB__PORT` |
| BROKER | `BROKER__USER`, `BROKER__PASSWORD`, `BROKER__HOST`, `BROKER__PORT` |
| API | `API__KEY`, `API__PORT` |
| WEBHOOK | `WEBHOOK__TIMEOUT`, `WEBHOOK__MAX_ATTEMPTS`, `WEBHOOK__INITIAL_DELAY` |
| OUTBOX | `OUTBOX__POLL_INTERVAL`, `OUTBOX__BATCH_SIZE`, `OUTBOX__SHUTDOWN_TIMEOUT` |
| GATEWAY | `GATEWAY__MIN_DELAY`, `GATEWAY__MAX_DELAY`, `GATEWAY__SUCCESS_RATE` |
| CONSUMER | `CONSUMER__MAX_ATTEMPTS`, `CONSUMER__INITIAL_DELAY` |

## Важные замечания

- **Domain vs ORM**: `domain/models.py` содержит плоские сущности (`Payment`, `OutboxMessage`); `infrastructure/models.py` — SQLAlchemy модели (`PaymentModel`, `OutboxModel`). Не путайте их.
- **Routes**: Определены в `api/v1/routers.py`, монтируются на `/api/v1` через `api/v1/main_router.py`.
- **`.env` vs `.env.test`**: `.env` содержит Docker-хостнеймы (`postgres`, `rabbitmq`) — тесты упадут, если не используется `.env.test`.
- **Ruff**: использует double quotes (`quote-style = "double"` в `pyproject.toml`).
- **Mypy**: strict mode; модули `faststream.*` и `tests.*` имеют ослабленные правила.
