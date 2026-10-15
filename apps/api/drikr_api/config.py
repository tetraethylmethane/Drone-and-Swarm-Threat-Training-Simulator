"""Environment-based configuration, validated at startup.

All settings use the ``DRIKR_`` prefix. Invalid or insecure configuration makes
the process exit with a clear message instead of starting in an unsafe state.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_SECRETS = {"change-me", "changeme", "secret", "replace-with-a-long-random-value"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DRIKR_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(description="SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/drikr")
    secret_key: SecretStr = Field(description="At least 32 characters; used to key token digests")

    session_ttl_minutes: int = Field(default=480, ge=5, le=24 * 60)
    session_idle_minutes: int = Field(default=60, ge=5, le=24 * 60)
    cookie_secure: bool = True
    cors_origins: list[str] = Field(default_factory=list)
    #: Trust X-Forwarded-For from the bundled reverse proxy. Only enable when the API
    #: is not reachable except through that proxy (as in docker-compose.yml).
    trust_proxy_headers: bool = False

    login_rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    lockout_threshold: int = Field(default=5, ge=1, le=100)
    lockout_minutes: int = Field(default=15, ge=1, le=24 * 60)

    heartbeat_grace_s: int = Field(default=15, ge=3, le=600)
    sweeper_interval_s: int = Field(default=10, ge=0, le=3600)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def _postgres_only(cls, v: str) -> str:
        if not v.startswith("postgresql+psycopg://"):
            raise ValueError(
                "database_url must use the postgresql+psycopg:// driver (PostgreSQL is the only supported database)"
            )
        return v

    @field_validator("secret_key")
    @classmethod
    def _secret_strength(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        if len(raw) < 32:
            raise ValueError("secret_key must be at least 32 characters")
        if raw.lower() in _PLACEHOLDER_SECRETS:
            raise ValueError("secret_key must not be a placeholder value")
        return v

    @model_validator(mode="after")
    def _production_rules(self) -> Self:
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError("cookie_secure must be true in production")
            if "dev_only" in self.secret_key.get_secret_value() or "dev_only" in self.database_url:
                raise ValueError("development credentials must not be used in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
