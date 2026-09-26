"""
FastAPI application entrypoint.

Wires together the app-wide infrastructure lifecycle:
  - configures logging once, at process start
  - blocks startup until PostgreSQL is reachable (hard dependency — fails
    fast rather than serving traffic that can't read/write data)
  - best-effort connects to Redis and Kafka at startup; either being
    temporarily unreachable is logged loudly but does not prevent the API
    from serving routes that don't need them (see /health/redis and
    /health/kafka for live status)
  - disposes all pooled connections cleanly on shutdown
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.routes import admin, auth, health, technicians, users
from app.api.webhooks import whatsapp
from app.core.database import connect_with_retry, dispose_async_engine, dispose_engine
from app.core.kafka import connect_with_retry as kafka_connect_with_retry
from app.core.kafka import dispose_kafka
from app.core.logging import configure_logging
from app.core.redis import connect_with_retry as redis_connect_with_retry
from app.core.redis import dispose_redis
from app.utils.exceptions import DatabaseConnectionError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    configure_logging()
    try:
        connect_with_retry()
    except DatabaseConnectionError:
        # Fail fast and loud — don't serve traffic with no DB.
        # In Docker/k8s this causes a clean crash-loop with a readable log,
        # rather than the app silently accepting requests it can't fulfill.
        raise
    redis_connect_with_retry()
    kafka_connect_with_retry()
    yield
    # --- Shutdown ---
    dispose_engine()
    await dispose_async_engine()
    dispose_redis()
    dispose_kafka()


app = FastAPI(title="fieldmind-ai", lifespan=lifespan)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(technicians.router)
app.include_router(admin.router)
app.include_router(whatsapp.router)

# Business-feature routers (bookings, service_requests, reviews, ...) are
# owned by their respective teams and are wired in as each becomes ready.
# users/technicians/admin above currently expose only the minimal
# auth-scoped endpoints (own profile, RBAC-gated reads) needed to
# exercise/test the authentication & authorization layer end-to-end — see
# docs/AUTH.md.
