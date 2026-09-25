from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    SECRET_KEY: str = Field(
        default="default-insecure-secret-key-change-in-production-min-32-chars",
        description="JWT secret key",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/yandex_driver"
    DATABASE_ECHO: bool = False

    REDIS_URL: str = "redis://localhost:6379/0"

    YANDEX_FLEET_BASE_URL: str = "https://fleet-api.taxi.yandex.net"
    YANDEX_CLIENT_ID: str | None = None
    YANDEX_API_KEY: str | None = None
    YANDEX_PARK_ID: str | None = None

    ORDER_SYNC_INTERVAL_SECONDS: int = 10
    DRIVER_SYNC_INTERVAL_SECONDS: int = 300
    VEHICLE_SYNC_INTERVAL_SECONDS: int = 600

    LOG_LEVEL: str = "INFO"

    @property
    def is_yandex_configured(self) -> bool:
        return bool(
            self.YANDEX_CLIENT_ID
            and self.YANDEX_API_KEY
            and self.YANDEX_PARK_ID
        )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
