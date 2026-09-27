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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/yandex_driver"
    )
    DATABASE_ECHO: bool = False

    REDIS_URL: str = "redis://localhost:6379/0"

    YANDEX_FLEET_BASE_URL: str = "https://fleet-api.taxi.yandex.net"
    YANDEX_CLIENT_ID: str | None = None
    YANDEX_API_KEY: str | None = None
    YANDEX_PARK_ID: str | None = None
    YANDEX_MOCK_MODE: bool = True
    YANDEX_ORDERS_LOOKBACK_DAYS: int = 7
    YANDEX_MAX_PAGES: int = 20
    YANDEX_MAX_RECORDS: int = 5000
    YANDEX_HTTP_CONNECT_TIMEOUT_SECONDS: float = 5.0
    YANDEX_HTTP_READ_TIMEOUT_SECONDS: float = 15.0
    YANDEX_RETRY_ATTEMPTS: int = 3
    PHONE_DEFAULT_COUNTRY_CODE: str = "996"

    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_BOT_BACKEND_URL: str = "http://127.0.0.1:8000"
    TELEGRAM_BOT_REQUEST_TIMEOUT_SECONDS: float = 10.0
    TELEGRAM_BOT_DB_PATH: str = ".data/telegram_bot.sqlite3"
    TELEGRAM_BOT_ORDERS_PAGE_SIZE: int = 5
    TELEGRAM_BOT_MODE: str = "polling"
    TELEGRAM_HTTP_PROXY: str | None = None
    TELEGRAM_WEBHOOK_BASE_URL: str = ""
    TELEGRAM_WEBHOOK_PATH: str = "/api/v1/telegram/webhook"
    TELEGRAM_WEBHOOK_SECRET: str | None = None
    TELEGRAM_WEBHOOK_AUTO_SETUP: bool = True
    TELEGRAM_MINI_APP_URL: str = ""
    TELEGRAM_MINI_APP_DEMO_MODE: bool = True

    ORDER_SYNC_INTERVAL_SECONDS: int = 10
    DRIVER_SYNC_INTERVAL_SECONDS: int = 300
    VEHICLE_SYNC_INTERVAL_SECONDS: int = 600

    MOBILE_ENABLED: bool = True
    MOBILE_DB_PATH: str = ".data/mobile.sqlite3"
    MOBILE_JWT_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    MOBILE_ORDER_WATCHER_ENABLED: bool = True
    MOBILE_ORDER_POLL_INTERVAL_SECONDS: int = Field(default=10, ge=5)
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CREDENTIALS_FILE: str = ""

    LOG_LEVEL: str = "INFO"

    @property
    def telegram_mini_app_url(self) -> str:
        if self.TELEGRAM_MINI_APP_URL:
            return self.TELEGRAM_MINI_APP_URL.rstrip("/") + "/"
        if self.TELEGRAM_WEBHOOK_BASE_URL:
            return self.TELEGRAM_WEBHOOK_BASE_URL.rstrip("/") + "/miniapp/"
        return ""

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
