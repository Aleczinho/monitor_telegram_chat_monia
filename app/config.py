import re
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "production", "test"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)

    github_webhook_secret: SecretStr | None = None
    github_repository: str = "healthdevio/projeto-itia-dois"

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    telegram_message_thread_id: int | None = None

    database_path: Path = Path("data/events.sqlite3")
    log_level: str = "INFO"
    webhook_max_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)

    worker_poll_interval_seconds: float = Field(default=1.0, gt=0, le=60)
    worker_lease_seconds: int = Field(default=60, ge=10, le=3600)
    worker_max_attempts: int = Field(default=8, ge=1, le=20)
    worker_retry_base_seconds: float = Field(default=2.0, gt=0, le=300)
    dedup_retention_days: int = Field(default=90, ge=30, le=3650)

    @field_validator("github_webhook_secret", "telegram_bot_token")
    @classmethod
    def validate_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None
        return value

    @field_validator("telegram_chat_id")
    @classmethod
    def validate_chat_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value

    @field_validator("github_repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", value):
            raise ValueError("must use the owner/repository format")
        return value

    @field_validator("telegram_message_thread_id", mode="before")
    @classmethod
    def parse_optional_thread_id(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be a standard Python logging level")
        return normalized

    def require_webhook_secret(self) -> SecretStr:
        if self.github_webhook_secret is None:
            raise ConfigurationError("GITHUB_WEBHOOK_SECRET is required by the API")
        return self.github_webhook_secret

    def require_telegram_credentials(self) -> tuple[SecretStr, str]:
        if self.telegram_bot_token is None:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required by the worker")
        if self.telegram_chat_id is None:
            raise ConfigurationError("TELEGRAM_CHAT_ID is required by the worker")
        return self.telegram_bot_token, self.telegram_chat_id
