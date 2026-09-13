"""
Application configuration.

Loads and validates all environment-driven settings for the service.
Fails fast at startup if required variables are missing or malformed,
rather than surfacing a confusing error later at first DB use.
"""
from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object. Values are sourced, in priority order, from:
    real environment variables > `.env` file > field defaults.
    """

    # --- App ---
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    APP_NAME: str = "fieldmind-ai"
    DEBUG: bool = False

    # --- Database (required — no defaults for credentials) ---
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    POSTGRES_SSLMODE: Literal["disable", "prefer", "require", "verify-full"] = "prefer"

    # --- Pool tuning ---
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30          # seconds to wait for a free connection
    DB_POOL_RECYCLE: int = 1800        # recycle connections every 30 min (avoids stale TCP conns)
    DB_ECHO: bool = False              # log every SQL statement — dev only
    DB_CONNECT_TIMEOUT: int = 10       # seconds before a connection attempt itself times out

    # --- Startup retry behavior ---
    DB_STARTUP_MAX_RETRIES: int = 5
    DB_STARTUP_RETRY_BASE_DELAY: float = 1.0   # seconds, doubles each attempt

    # --- Authentication (JWT) ---
    # No default — a missing secret must fail application startup loudly
    # rather than silently signing tokens with a predictable value (same
    # posture as POSTGRES_PASSWORD above). Set via `.env` locally; a real
    # secrets manager in staging/production.
    JWT_SECRET_KEY: str
    # Deliberately a closed set, not a free-form string: token verification
    # (app/core/security.py) passes this as the `algorithms=` allow-list to
    # the JWT library, which is what actually prevents an attacker from
    # forcing verification down an unintended/weaker algorithm.
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Redis ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_MAX_CONNECTIONS: int = 20
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_STARTUP_MAX_RETRIES: int = 5
    REDIS_STARTUP_RETRY_BASE_DELAY: float = 1.0

    # --- Kafka ---
    # Host-side bootstrap address (FastAPI running on the developer machine).
    # Containers on fieldmind-network use kafka:29092 instead — see docs/KAFKA.md.
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CLIENT_ID: str = "fieldmind-backend"
    KAFKA_CONSUMER_GROUP_ID: str = "fieldmind-backend"
    KAFKA_SECURITY_PROTOCOL: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = "PLAINTEXT"
    KAFKA_PRODUCER_ACKS: Literal["0", "1", "all"] = "all"          # "all" — no ack loss on leader failover
    KAFKA_PRODUCER_LINGER_MS: int = 20
    KAFKA_PRODUCER_MAX_RETRIES: int = 5
    KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS: int = 30000
    KAFKA_CONSUMER_AUTO_OFFSET_RESET: Literal["earliest", "latest"] = "earliest"
    KAFKA_CONSUMER_SESSION_TIMEOUT_MS: int = 45000
    KAFKA_STARTUP_MAX_RETRIES: int = 5
    KAFKA_STARTUP_RETRY_BASE_DELAY: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("POSTGRES_PORT")
    @classmethod
    def _validate_port(cls, v: int) -> int:
        if not (0 < v < 65536):
            raise ValueError(f"POSTGRES_PORT out of valid range: {v}")
        return v

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _validate_jwt_secret_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v

    @model_validator(mode="after")
    def _reject_weak_production_secrets(self) -> "Settings":
        """
        Extra guard specifically for production: a secret that merely passes
        the length check above could still be an obvious placeholder copied
        from `.env.example` (e.g. "changeme..."). Fail startup rather than
        run production with a guessable signing key.
        """
        if self.is_production:
            lowered = self.JWT_SECRET_KEY.lower()
            weak_markers = ("changeme", "change-me", "example", "placeholder", "secret-key", "insecure")
            if any(marker in lowered for marker in weak_markers):
                raise ValueError(
                    "JWT_SECRET_KEY looks like a placeholder value — set a real, "
                    "randomly-generated secret before running in production"
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def _build_url(self, driver: str) -> str:
        # URL-encode user/password — safe for special characters (@, :, /, etc.)
        user = quote_plus(self.POSTGRES_USER)
        pwd = quote_plus(self.POSTGRES_PASSWORD)
        return (
            f"postgresql+{driver}://{user}:{pwd}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL(self) -> str:
        """Sync URL — used by SQLAlchemy engine, Alembic, Celery workers."""
        return self._build_url("psycopg2")

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Async URL — used by FastAPI async routes / async session."""
        return self._build_url("asyncpg")

    @property
    def db_connect_args(self) -> dict:
        """Driver-level connect args (sync/psycopg2)."""
        args: dict = {"connect_timeout": self.DB_CONNECT_TIMEOUT}
        if self.POSTGRES_SSLMODE != "disable":
            args["sslmode"] = self.POSTGRES_SSLMODE
        return args

    @property
    def REDIS_URL(self) -> str:
        """redis://[:password@]host:port/db — password URL-encoded if set."""
        auth = f":{quote_plus(self.REDIS_PASSWORD)}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance. Using a function (rather than a bare module-level
    singleton) makes it easy to override in tests via dependency_overrides
    or by clearing the cache with get_settings.cache_clear().
    """
    return Settings()


settings = get_settings()