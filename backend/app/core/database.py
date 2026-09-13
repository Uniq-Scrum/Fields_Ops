"""
Database engine, session management, and connection health utilities.

Provides:
- Sync engine/session (for FastAPI routes, Celery tasks, Kafka consumers, scripts)
- Async engine/session (for async FastAPI routes)
- Retry-with-backoff connection check for use at application startup
- Pool event hooks for observability
- A FastAPI dependency (`get_db`) and a plain context manager (`get_db_context`)
"""
import logging
import time
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.utils.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models (Alembic autogenerate target)."""
    pass


# --- Sync engine (routes, Celery tasks, Kafka consumers, scripts) ---
engine: Engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,           # discard dead connections transparently before use
    echo=settings.DB_ECHO,
    connect_args=settings.db_connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

# --- Async engine (async FastAPI routes) ---
async_engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=settings.DB_ECHO,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# --- Pool observability ---
@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, connection_record) -> None:  # noqa: ANN001
    logger.debug("New DB connection established (pid=%s)", id(dbapi_conn))


@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_conn, connection_record, connection_proxy) -> None:  # noqa: ANN001
    logger.debug("Connection checked out from pool")


@event.listens_for(engine, "checkin")
def _on_checkin(dbapi_conn, connection_record) -> None:  # noqa: ANN001
    logger.debug("Connection returned to pool")


# --- FastAPI dependency (sync) ---
def get_db() -> Generator[Session, None, None]:
    """
    Request-scoped sync session for FastAPI route dependencies.
    Rolls back on error, always closes, never leaks connections.
    """
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


# --- FastAPI dependency (async) ---
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped async session for async route dependencies."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        except SQLAlchemyError:
            await db.rollback()
            raise


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Sync session for use outside FastAPI's DI system — Celery tasks,
    Kafka consumers, one-off scripts. Commits on success, rolls back on error.

    Usage:
        with get_db_context() as db:
            db.add(obj)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def check_db_connection() -> bool:
    """
    Single lightweight connectivity check (e.g. for a `/health` endpoint).
    Never raises — returns True/False so callers decide how to respond.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as e:
        logger.error("Database health check failed: %s", e)
        return False


def check_db_connection_verbose() -> dict:
    """
    Health check with latency and pool stats, for a detailed `/health/db` endpoint.
    """
    pool = engine.pool
    start = time.monotonic()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except SQLAlchemyError as e:
        return {"status": "error", "detail": str(e)}


def connect_with_retry() -> None:
    """
    Blocking connection check with exponential backoff, meant to be called
    once at application startup. Postgres (esp. in Docker Compose / k8s) may
    still be initializing when the API container starts — this gives it a
    chance to come up instead of crash-looping on the first failed attempt.

    Raises DatabaseConnectionError if all retries are exhausted.
    """
    max_retries = settings.DB_STARTUP_MAX_RETRIES
    delay = settings.DB_STARTUP_RETRY_BASE_DELAY

    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection established (attempt %d/%d)", attempt, max_retries)
            return
        except OperationalError as e:
            if attempt == max_retries:
                logger.critical(
                    "Database connection failed after %d attempts: %s", max_retries, e
                )
                raise DatabaseConnectionError(
                    f"Could not connect to database after {max_retries} attempts"
                ) from e
            logger.warning(
                "Database connection attempt %d/%d failed: %s — retrying in %.1fs",
                attempt, max_retries, e, delay,
            )
            time.sleep(delay)
            delay *= 2  # exponential backoff


def dispose_engine() -> None:
    """Cleanly release all pooled connections. Call on application shutdown."""
    engine.dispose()
    logger.info("Database engine disposed")


async def dispose_async_engine() -> None:
    """Async counterpart of dispose_engine — call on application shutdown."""
    await async_engine.dispose()
    logger.info("Async database engine disposed")