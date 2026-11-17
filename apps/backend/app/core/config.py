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
    cloudflare_account_id: str = ""
    cloudflare_ai_token: str = ""
    anthropic_api_key: str = ""
    ai_daily_calls_free: int = 50

    # Object storage (SeaweedFS locally, R2 in staging/production)
    s3_endpoint: str = "http://objectstore:8333"
    s3_presign_endpoint: str = ""  # host the browser uses for presigned PUTs; empty = s3_endpoint
    s3_access_key: str = "rsv-local"
    s3_secret_key: str = "rsv-local-secret"  # noqa: S105 - local SeaweedFS only
    s3_region: str = "auto"
    s3_bucket_raw: str = "rsv-raw"
    s3_bucket_public: str = "rsv-public"
    media_public_base: str = "http://localhost:8080/rsv-public"

    # Payments (Phase 6) — empty keys = sandbox fake provider, never in production
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Calls (Phase 7)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    health_check_timeout_s: float = Field(default=2.0, gt=0)
    # Abuse limits (Blueprint 12.2). Only raise for local end-to-end runs; never in staging/production.
    rate_limit_signup_per_hour: int = Field(default=10, ge=1)

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
