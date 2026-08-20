from os import environ

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DB(BaseModel):
    name: str
    user: str
    password: str
    host: str
    port: int
    pool_max_size: int = 20
    pool_max_overflow: int = 10

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class Broker(BaseModel):
    user: str
    password: str
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/"


class Outbox(BaseModel):
    poll_interval: float = 1.0
    batch_size: int = 100
    shutdown_timeout: float = 5.0


class Gateway(BaseModel):
    min_delay: float = 2.0
    max_delay: float = 5.0
    success_rate: float = 0.9


class Webhook(BaseModel):
    timeout: int = 10
    max_attempts: int = 3
    initial_delay: float = 1.0


class Consumer(BaseModel):
    max_attempts: int = 3
    initial_delay: float = 1.0


class API(BaseModel):
    key: str
    port: int = 80


class Settings(BaseSettings):
    """Root application settings."""

    model_config = SettingsConfigDict(
        env_file=environ.get("SETTINGS_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    db: DB
    broker: Broker
    outbox: Outbox
    gateway: Gateway
    webhook: Webhook
    consumer: Consumer
    api: API
