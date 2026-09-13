"""
Redis connection pool, health checks, and lifecycle management.

A single process-wide connection pool is created at import time and shared
across the application (FastAPI routes, Celery tasks, Kafka consumers).
redis-py's client is safe to share across threads when backed by a pool,
so there is no per-request connect/disconnect overhead.
"""
import logging
import time
from typing import Generator

import redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
    health_check_interval=30,
    decode_responses=True,
)

redis_client = redis.Redis(connection_pool=pool)


def get_redis() -> Generator[redis.Redis, None, None]:
    """FastAPI dependency — yields the shared, pooled client."""
    yield redis_client


def check_redis_connection() -> bool:
    """Single lightweight connectivity check (e.g. for a `/health` endpoint)."""
    try:
        return bool(redis_client.ping())
    except RedisError as e:
        logger.error("Redis health check failed: %s", e)
        return False


def check_redis_connection_verbose() -> dict:
    """Health check with latency and server stats, for a `/health/redis` endpoint."""
    start = time.monotonic()
    try:
        redis_client.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        info = redis_client.info(section="clients")
        memory = redis_client.info(section="memory")
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "max_pool_connections": pool.max_connections,
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": memory.get("used_memory_human"),
        }
    except RedisError as e:
        return {"status": "error", "detail": str(e)}


def connect_with_retry() -> None:
    """
    Blocking Redis connectivity check with exponential backoff, meant to be
    called once at application startup.

    Unlike the database, Redis is treated as a soft dependency here: if it
    is still unreachable after all retries, the failure is logged loudly
    but startup continues in a degraded mode rather than crash-looping the
    whole API over a cache/broker outage. Real-time status stays visible
    via `/health/redis`.
    """
    max_retries = settings.REDIS_STARTUP_MAX_RETRIES
    delay = settings.REDIS_STARTUP_RETRY_BASE_DELAY

    for attempt in range(1, max_retries + 1):
        try:
            redis_client.ping()
            logger.info("Redis connection established (attempt %d/%d)", attempt, max_retries)
            return
        except RedisError as e:
            if attempt == max_retries:
                logger.error(
                    "Redis connection failed after %d attempts: %s — starting in degraded mode",
                    max_retries, e,
                )
                return
            logger.warning(
                "Redis connection attempt %d/%d failed: %s — retrying in %.1fs",
                attempt, max_retries, e, delay,
            )
            time.sleep(delay)
            delay *= 2  # exponential backoff


def dispose_redis() -> None:
    """Cleanly release all pooled Redis connections. Call on application shutdown."""
    pool.disconnect()
    logger.info("Redis connection pool disposed")
