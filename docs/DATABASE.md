# Database — PostgreSQL + PostGIS

## Overview

FieldMind AI uses **PostgreSQL 16 with PostGIS 3.4** (`postgis/postgis:16-3.4`)
for all relational and geospatial data (technician locations, service
request geometry, etc.).

- Container: `fieldmind-postgres`
- Defined in: `infrastructure/docker/docker-compose.yml` (source of truth)
- Host connection: `localhost:5432`
- In-container connection (from other containers on `fieldmind-network`): `postgres:5432`

## Starting / stopping

```
docker compose up -d postgres      # start just Postgres
docker compose up -d               # start all infrastructure
docker compose down                # stop (data volume is preserved)
docker compose down -v             # stop AND delete all data (destructive)
```

Data persists in the named volume `fieldmind-postgres-data`, not in the
container filesystem — the container can be recreated at any time without
losing data.

## Environment variables

Set in `.env` (copy from `.env.example`):

| Variable            | Default              | Used by                          |
|---------------------|-----------------------|-----------------------------------|
| `POSTGRES_HOST`     | `localhost`           | backend (`config.py`)             |
| `POSTGRES_PORT`     | `5432`                | backend + compose port mapping    |
| `POSTGRES_DB`       | `fieldmind`           | backend + compose init            |
| `POSTGRES_USER`     | `fieldmind`           | backend + compose init            |
| `POSTGRES_PASSWORD` | *(required, no default)* | backend + compose init        |
| `POSTGRES_SSLMODE`  | `disable`              | backend (sync driver connect args)|

`POSTGRES_PASSWORD` has no fallback in `infrastructure/docker/docker-compose.yml` —
`docker compose up` fails fast with a clear error if it isn't set, rather
than silently starting with a weak or empty credential.

Additional pool-tuning variables (all optional, with sane defaults) are
documented inline in `backend/app/core/config.py`: `DB_POOL_SIZE`,
`DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, `DB_ECHO`,
`DB_CONNECT_TIMEOUT`, `DB_STARTUP_MAX_RETRIES`, `DB_STARTUP_RETRY_BASE_DELAY`.

## FastAPI ↔ PostgreSQL connection

Implemented in `backend/app/core/config.py` and `backend/app/core/database.py`:

- **Configuration** (`config.py`): a `pydantic-settings` `Settings` class
  loads and validates all DB variables from `.env`/environment at process
  start. Credentials are required fields with no default — the app fails
  immediately at import time if they're missing, rather than surfacing a
  confusing error on first query. `DATABASE_URL` (sync, psycopg2) and
  `ASYNC_DATABASE_URL` (async, asyncpg) are built with the user/password
  URL-encoded so special characters (`@`, `:`, `/`) don't break the URL.
- **Engine & pooling** (`database.py`): both a sync `Engine` (for routes,
  Celery tasks, Kafka consumers, scripts) and an async engine (for async
  routes) are created once at import time with a **bounded connection
  pool** (`pool_size` + `max_overflow`, not unlimited connections),
  `pool_pre_ping=True` (transparently discards dead connections before
  use), and `pool_recycle` (avoids stale long-lived TCP connections).
- **Sessions**: `get_db()` / `get_async_db()` are FastAPI dependencies that
  yield a request-scoped session, roll back on `SQLAlchemyError`, and
  always close in a `finally` block — no connection is ever leaked.
  `get_db_context()` is the equivalent context manager for code outside
  FastAPI's DI system (Celery tasks, Kafka consumers, one-off scripts).
- **Startup connectivity check**: `connect_with_retry()` blocks app
  startup with exponential backoff (`DB_STARTUP_MAX_RETRIES`,
  `DB_STARTUP_RETRY_BASE_DELAY`) to tolerate Postgres still initializing
  when the API starts. If all retries are exhausted it raises
  `DatabaseConnectionError`, and `backend/app/main.py`'s `lifespan` handler
  re-raises it — this fails the process fast and loud (a clean crash-loop
  with a readable log) instead of serving traffic with no working
  database.
- **Error handling**: `SQLAlchemyError` is caught specifically (never a
  bare `except:`), logged, and re-raised as-is or wrapped in
  `DatabaseConnectionError`/`DatabaseTimeoutError`
  (`backend/app/utils/exceptions.py`) — raw driver exceptions and
  connection strings are never returned to API consumers.
- **Shutdown**: `dispose_engine()` / `dispose_async_engine()` are called in
  `main.py`'s `lifespan` shutdown phase to cleanly release all pooled
  connections.

## Health / readiness endpoints

Defined in `backend/app/api/routes/health.py`:

| Endpoint      | Purpose                                                        |
|---------------|-----------------------------------------------------------------|
| `GET /health`      | Liveness — is the process up? No DB dependency.            |
| `GET /health/db`   | Readiness — actual `SELECT 1` against Postgres, with latency and pool stats. |
| `GET /health/ready`| Simple boolean readiness for orchestrators (200/503).       |

## Verifying manually

```
# Container health
docker compose ps postgres

# psql shell
docker exec -it fieldmind-postgres psql -U fieldmind -d fieldmind

# Confirm PostGIS is available
docker exec fieldmind-postgres psql -U fieldmind -d fieldmind -c "SELECT PostGIS_Version();"

# From the host, with psql installed locally (optional)
psql -h localhost -p 5432 -U fieldmind -d fieldmind

# From the running FastAPI app
curl http://127.0.0.1:8000/health/db
```

## Schema & migrations

**Alembic is the schema source of truth**, configured under `backend/`:

- `backend/alembic.ini` / `backend/alembic/env.py` — the DB URL is never
  hardcoded here; `env.py` builds it from the same `Settings` object
  (`app.core.config.settings`) the application itself uses.
- `backend/alembic/versions/` — one revision per schema change. See
  [docs/AUTH.md](AUTH.md) for the `users`/`field_officers` migrations
  (enums, tables, constraints, triggers) added for the auth/user module.

Commands (run from `backend/`, with the venv activated):

```
alembic upgrade head        # apply all pending migrations
alembic downgrade -1        # revert the most recent migration
alembic current              # show the currently applied revision
alembic revision -m "..."    # create a new empty revision
```

`database/schemas/` (`users.sql`, `field_officers.sql`,
`service_requests.sql`, `customer_reviews.sql`) and
`database/indexes/postgis_indexes.sql` are pre-Alembic design stubs and
were intentionally left as-is — they are not applied against the database
by anything and are superseded by the Alembic migrations above for any
table they overlap with.

## Security notes

- Application credentials come only from environment variables — never
  hardcoded in source, never committed (`.env` is git-ignored).
- Errors returned to API consumers never include connection strings,
  passwords, or raw driver tracebacks.
- **Local-dev simplification, documented for production hardening:**
  `POSTGRES_USER` is currently used both to initialize the database and by
  the application at runtime, i.e. one role for both purposes. Before
  production, split this into a bootstrap/migration role (used only to run
  DDL) and a dedicated least-privilege application role — granted
  `CONNECT`/`USAGE` and row-level CRUD only, never `CREATEDB`/`CREATEROLE`/
  superuser. Postgres' official image supports this via a
  `docker-entrypoint-initdb.d/*.sql` script that runs once on first init.
- Local Postgres binds to `127.0.0.1:5432` — not reachable from other
  machines on the network.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `docker compose up` fails with `POSTGRES_PASSWORD must be set in .env` | Create `.env` from `.env.example` (see docs/ARCHITECTURE.md). |
| Container stuck `starting` / not `healthy` | `docker compose logs postgres` — usually still initializing on first run (creating the data directory); wait for `pg_isready` to pass. |
| FastAPI fails at startup with `DatabaseConnectionError` | Confirm `docker compose ps` shows postgres `healthy`, and `.env` `POSTGRES_*` values match the running container's. |
| `psql: FATAL: password authentication failed` | `.env` value differs from what the container was **first** initialized with — Postgres only applies `POSTGRES_PASSWORD` on first init of an empty volume. Either match `.env` to the volume's original password, or reset with `docker compose down -v` (destructive) and start fresh. |
| Port `5432` already in use | Another Postgres (local install or another project) is bound to it. Set `POSTGRES_PORT` in `.env` to a free port, e.g. `5433`. |
