# Kafka

## Overview

FieldMind AI uses **Confluent Platform Kafka 7.6.1** with **ZooKeeper**
(this project has not adopted KRaft) for event-driven communication
(dispatch events, job events, payment events — see `workers/kafka/`).

- Containers: `fieldmind-kafka`, `fieldmind-zookeeper`
- Defined in: `infrastructure/docker/docker-compose.yml` (source of truth)
- Host connection (FastAPI running on the developer machine): `localhost:9092`
- In-container connection (other containers on `fieldmind-network`, e.g. a
  future dockerized worker): `kafka:29092`
- ZooKeeper has **no host port** — only Kafka needs to reach it, over
  `fieldmind-network`.

## Starting / stopping

```
docker compose up -d zookeeper kafka   # start just Kafka + its dependency
docker compose up -d                   # start all infrastructure
docker compose down                    # stop (data volumes preserved)
docker compose down -v                 # stop AND delete all data (destructive)
```

Kafka's log segments persist in `fieldmind-kafka-data`; ZooKeeper's state
in `fieldmind-zookeeper-data` / `fieldmind-zookeeper-logs`.

## Listeners — why there are two

Kafka is configured with two listeners so both the host and other
containers can reach it, without confusing the two:

| Listener   | Advertised as         | Used by                                  |
|------------|------------------------|--------------------------------------------|
| `EXTERNAL` | `localhost:9092`       | FastAPI / scripts running on the host      |
| `INTERNAL` | `kafka:29092`          | Other containers on `fieldmind-network`    |

`KAFKA_INTER_BROKER_LISTENER_NAME=INTERNAL` — broker-to-broker traffic (not
relevant with one broker, but keeps the config correct if a second broker
is ever added) uses the internal listener, never the host-facing one.

## Environment variables

| Variable                    | Default                | Used by |
|------------------------------|-------------------------|---------|
| `KAFKA_BOOTSTRAP_SERVERS`    | `localhost:9092`        | backend (`config.py`, host-side clients) |
| `KAFKA_EXTERNAL_PORT`        | `9092`                  | compose port mapping + advertised listener |
| `KAFKA_CLIENT_ID`            | `fieldmind-backend`     | producer/consumer identification in broker logs |
| `KAFKA_CONSUMER_GROUP_ID`    | `fieldmind-backend`     | default consumer group |

Producer/consumer reliability tuning (all optional, with sane defaults) is
documented inline in `backend/app/core/config.py`: `KAFKA_SECURITY_PROTOCOL`,
`KAFKA_PRODUCER_ACKS`, `KAFKA_PRODUCER_LINGER_MS`,
`KAFKA_PRODUCER_MAX_RETRIES`, `KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS`,
`KAFKA_CONSUMER_AUTO_OFFSET_RESET`, `KAFKA_CONSUMER_SESSION_TIMEOUT_MS`.

## Python integration

Implemented in `backend/app/core/kafka.py` using `confluent-kafka`
(librdkafka bindings — matches the Confluent broker):

- **Producer** (`get_producer()`): a process-wide singleton, configured
  with `acks=all` (no acknowledgement loss on leader failover) and
  `enable.idempotence=True` (no duplicate/out-of-order writes on retry).
  `retries` and `delivery.timeout.ms` bound retry behavior — delivery
  eventually fails loudly (logged via the delivery-report callback)
  instead of retrying forever.
- **Consumers** (`create_consumer(topics, group_id)`): built per
  consumer-group by callers in `workers/kafka/consumers/`, with
  `enable.auto.commit=False` — callers commit offsets explicitly after
  successfully processing a message, which is what makes
  application-level idempotent processing possible (at-least-once
  delivery, no silent message loss on a crash mid-processing).
  `close_consumer()` closes a consumer cleanly so the group rebalances
  immediately rather than waiting out the session timeout.
- **Health checks**: `check_kafka_connection()` /
  `check_kafka_connection_verbose()` query cluster metadata via
  `AdminClient.list_topics()` — a real broker round-trip, not just "is the
  port open."
- **Startup**: `connect_with_retry()` is called from `main.py`'s lifespan
  with exponential backoff. Kafka is treated as a **soft dependency** —
  if unreachable after all retries, this logs an error and the API starts
  in degraded mode rather than crash-looping (unlike Postgres, which is a
  hard gate). Live status is always visible at `/health/kafka`.
- **Shutdown**: `dispose_kafka()` calls `producer.flush()` with a timeout
  so in-flight messages are delivered (or their failure logged) before the
  process exits, instead of being silently dropped.

## Health / readiness endpoint

`GET /health/kafka` (`backend/app/api/routes/health.py`) returns broker
count, topic count, and latency, with a `503` if the broker is unreachable.

## Verifying manually

```
# Container health
docker compose ps kafka zookeeper

# List topics
docker exec fieldmind-kafka kafka-topics --bootstrap-server localhost:9092 --list

# Create a topic explicitly
docker exec fieldmind-kafka kafka-topics --bootstrap-server localhost:9092 \
  --create --topic dispatch-events --partitions 3 --replication-factor 1

# Produce a test message
echo "hello" | docker exec -i fieldmind-kafka kafka-console-producer \
  --bootstrap-server localhost:9092 --topic dispatch-events

# Consume it back
docker exec fieldmind-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 --topic dispatch-events \
  --from-beginning --max-messages 1

# From the running FastAPI app
curl http://127.0.0.1:8000/health/kafka
```

## Production considerations (do not treat local dev as production-ready)

This local/staging setup is deliberately simple. Before production:

- **Security**: switch `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP` away from
  `PLAINTEXT` to TLS (`SSL`) and/or SASL (`SASL_SSL`/`SASL_PLAINTEXT`) for
  both listeners, and set `KAFKA_SECURITY_PROTOCOL` correspondingly on the
  Python client side (`backend/app/core/config.py`). Plaintext, unauthenticated
  Kafka must never be exposed outside an isolated development network.
- **High availability**: a single broker (`KAFKA_BROKER_ID: 1`, all
  replication factors `1`) is a single point of failure and **is not**
  highly-available infrastructure. Production needs ≥3 brokers with
  `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR`,
  `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR`, and per-topic
  `replication-factor` raised to match (typically 3), plus `min.insync.replicas`
  tuned so writes aren't acknowledged by an under-replicated cluster.
  ZooKeeper itself would also need an ensemble (3 or 5 nodes) rather than
  a single instance.
- **Topic management**: disable `KAFKA_AUTO_CREATE_TOPICS_ENABLE` and
  create topics explicitly (via `kafka-topics` or infra-as-code) with
  deliberate partition counts and retention policies.
- **Resource limits**: `KAFKA_HEAP_OPTS`/`ZOOKEEPER`'s `KAFKA_HEAP_OPTS`
  are set conservatively for a laptop (256–512MB); size for real
  production throughput and available host memory.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `fieldmind-zookeeper` unhealthy | `docker compose logs zookeeper` — the `ruok` four-letter command is disabled by default on this image and is **not** re-enabled by `ZOOKEEPER_4LW_COMMANDS_WHITELIST` (confirmed not honored on `cp-zookeeper:7.6.1`); the healthcheck therefore uses `srvr` instead. If this ever regresses, verify with `docker exec fieldmind-zookeeper sh -c "echo srvr \| nc -w 2 localhost 2181"`. |
| `fieldmind-kafka` never becomes healthy / `Error dependency zookeeper failed to start` | Kafka's `depends_on: zookeeper: condition: service_healthy` blocks until ZooKeeper reports healthy first — fix ZooKeeper's health before looking at Kafka. |
| Host client (FastAPI) can't connect, but `docker exec` into Kafka works | Confirm you're using `localhost:9092` (the `EXTERNAL` listener), not `kafka:29092` (only valid *inside* `fieldmind-network`). |
| A dockerized worker/consumer can't connect | It must use `kafka:29092` (`INTERNAL` listener) and be attached to the `fieldmind-network` network — `localhost:9092` does not resolve to the broker from inside another container. |
| Port `9092` already in use | Another Kafka broker is bound to it. Set `KAFKA_EXTERNAL_PORT` in `.env` to a free port. |
| Messages appear lost | Check `check_kafka_connection_verbose()` / `/health/kafka` for broker health, and application logs for delivery-report errors from `backend/app/core/kafka.py`'s `_delivery_report` — failed deliveries are logged, never silently dropped. |
