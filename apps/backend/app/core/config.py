"""Central settings. Every value comes from the environment (prefix RSV_)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]

_WEAK_SECRETS = {"", "change-me", "changeme", "secret", "dev", "test"}
_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RSV_", env_file=".env", extra="ignore")

    env: Environment = "local"
    app_name: str = "RedStarVibe"
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:8080"

    secret_key: str = "change-me"  # noqa: S105 - local default; rejected in staging/production
    field_encryption_key: str = "change-me"

    database_url: str = "postgresql+asyncpg://rsv:rsv@db:5432/rsv"
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_statement_timeout_ms: int = 5000
    # ADR 0002: behind PgBouncer (transaction mode) the asyncpg statement cache must be off.
    db_pgbouncer: bool = False

    redis_url: str = "redis://redis:6379/0"

    ai_provider: Literal["none", "cloudflare", "anthropic"] = "none"

    health_check_timeout_s: float = Field(default=2.0, gt=0)

    @property
    def is_deployed(self) -> bool:
        return self.env in ("staging", "production")

    @model_validator(mode="after")
    def _refuse_weak_secrets(self) -> "Settings":
        """Staging and production refuse to start with weak or default secrets."""
        if self.is_deployed:
            for name in ("secret_key", "field_encryption_key"):
                value = getattr(self, name)
                if value.lower() in _WEAK_SECRETS or len(value) < _MIN_SECRET_LENGTH:
                    raise ValueError(f"RSV_{name.upper()} is weak or missing; refusing to start in {self.env}")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
