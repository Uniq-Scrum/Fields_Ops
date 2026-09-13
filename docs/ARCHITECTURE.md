# Infrastructure Architecture

This document describes FieldMind AI's local development / staging
infrastructure: what runs where, how services talk to each other, and how
to reproduce the environment on a new machine.

For service-specific detail, see [docs/DATABASE.md](DATABASE.md) and
[docs/KAFKA.md](KAFKA.md).

## Overview

```
                         Developer machine
  ┌───────────────────────────────────────────────────────────────┐
  │                                                                 │
  │   FastAPI (uvicorn)              Docker network: fieldmind-network
  │   runs directly on host    ┌─────────────────────────────────┐ │
  │        │                   │                                 │ │
  │        │ localhost:5432    │  fieldmind-postgres (PostGIS)   │ │
  │        ├──────────────────►│  fieldmind-redis                │ │
  │        │ localhost:6379    │  fieldmind-zookeeper (internal) │ │
  │        │                   │  fieldmind-kafka                │ │
  │        │ localhost:9092    │                                 │ │
  │        └──────────────────►│                                 │ │
  │                             └─────────────────────────────────┘ │
  └───────────────────────────────────────────────────────────────┘
```

- Every infrastructure service (PostgreSQL+PostGIS, Redis, ZooKeeper,
  Kafka) runs as its **own container** — never combined into a single
  image or container. Each can be restarted, rebuilt, or scaled
  independently.
- FastAPI runs **directly on the developer's machine** (not in Docker) so
  local iteration doesn't require a rebuild loop. It reaches infrastructure
  via `localhost` host ports.
- Containers reach each other via **Docker service names** on the shared
  `fieldmind-network` bridge network (e.g. `kafka:29092`, not
  `localhost:29092`).

## Source of truth for infrastructure

**`infrastructure/docker/docker-compose.yml` is the single source of truth**
for all infrastructure service definitions. It owns:

- Service images, environment, healthchecks, resource bounds
- Named volumes (persistent data)
- The `fieldmind-network` Docker network

The root **`docker-compose.yml`** defines no services of its own — it uses
the Compose `include:` directive to pull in the infrastructure file, purely
so `docker compose up -d` also works from the repository root without an
extra `-f` flag. There is exactly one definition of each service; nothing
is duplicated between the two files.

Application code lives under `backend/app/`; infrastructure configuration
lives under `infrastructure/`. Business logic (routes, services, models)
must not encode infrastructure specifics (hosts, ports, credentials) —
those come from environment variables via `backend/app/core/config.py`.

## Services

| Service     | Container name        | Image                              | Host port(s)         |
|-------------|------------------------|-------------------------------------|-----------------------|
| PostgreSQL  | `fieldmind-postgres`  | `postgis/postgis:16-3.4`            | `127.0.0.1:5432`      |
| Redis       | `fieldmind-redis`     | `redis:7.4.1`                       | `127.0.0.1:6379`      |
| ZooKeeper   | `fieldmind-zookeeper` | `confluentinc/cp-zookeeper:7.6.1`   | none (internal only) |
| Kafka       | `fieldmind-kafka`     | `confluentinc/cp-kafka:7.6.1`       | `127.0.0.1:9092`      |

Host ports are bound to `127.0.0.1` only (not `0.0.0.0`) — they are
reachable from the developer machine but not from other machines on the
network. ZooKeeper has no host port at all: nothing outside the Docker
network needs to reach it, only Kafka does, over `fieldmind-network`.

## Reproducing the environment (new developer setup)

A new developer does **not** need to install PostgreSQL, Redis, Kafka, or
ZooKeeper on their machine. Steps:

1. Clone the repository.
2. Copy the environment template:
   ```
   cp .env.example .env
   ```
3. Start infrastructure:
   ```
   docker compose up -d
   ```
4. Confirm everything is healthy:
   ```
   docker compose ps
   ```
   All four containers should show `(healthy)`.
5. Install backend dependencies and run the API on the host:
   ```
   cd backend
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
6. Verify connectivity from the running API:
   ```
   curl http://127.0.0.1:8000/health/db
   curl http://127.0.0.1:8000/health/redis
   curl http://127.0.0.1:8000/health/kafka
   ```

## Design decisions and known limitations (read before extending)

- **Single-node infrastructure.** One Postgres instance, one Kafka broker.
  This is a local development / staging setup — it is explicitly **not**
  highly-available production infrastructure. Production requires a
  replicated/managed Postgres instance and a multi-broker Kafka cluster
  (see docs/KAFKA.md for what changes).
- **PLAINTEXT Kafka, no auth.** Fine on an isolated developer machine with
  loopback-only port binding. Production must use TLS + SASL — see
  docs/KAFKA.md.
- **Single Postgres role.** `POSTGRES_USER` is used both to initialize the
  database and by the application. This keeps local setup simple, but it
  is not least-privilege. Before production, split this into a
  bootstrap/migration role and a restricted application role (`CONNECT` +
  `USAGE`/CRUD grants only, no `CREATEDB`/`CREATEROLE`), enforced via a
  `docker-entrypoint-initdb.d` init script or your migration tool.
- **Redis has no auth in local dev.** Mitigated by binding to `127.0.0.1`
  only. `backend/app/core/config.py` already supports `REDIS_PASSWORD` for
  environments where `requirepass`/ACLs are configured.
- **`KAFKA_AUTO_CREATE_TOPICS_ENABLE=true`.** Convenient for local
  development; staging/production should disable this and create topics
  explicitly so partition counts and retention are deliberate.

## Observability

`infrastructure/monitoring/grafana/` and `infrastructure/monitoring/prometheus/`
are reserved for metrics/dashboards as the project matures. The current
infrastructure is designed to be observed cleanly without them:

- Every container has a real healthcheck (not just "process is running") —
  see `docker compose ps`.
- `backend/app/core/{database,redis,kafka}.py` each expose a
  `check_*_connection_verbose()` function returning latency and basic
  stats, surfaced at `/health/db`, `/health/redis`, `/health/kafka`.
- Logging is configured once, centrally, in `backend/app/core/logging.py` —
  no module calls `logging.basicConfig()` on its own. Nothing in the
  codebase logs credentials or full connection strings.

## Troubleshooting

See the "Troubleshooting" sections in [docs/DATABASE.md](DATABASE.md) and
[docs/KAFKA.md](KAFKA.md) for service-specific issues. General commands:

```
docker compose ps                      # container status + health
docker compose logs -f <service>       # tail one service's logs
docker compose logs -f                 # tail all services
docker network inspect fieldmind-network
docker volume ls --filter name=fieldmind
```
