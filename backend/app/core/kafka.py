"""
Kafka producer/consumer factories, health checks, and lifecycle management.

Uses confluent-kafka (librdkafka bindings) to match the project's Confluent
Platform 7.6.1 broker. A single producer instance is shared process-wide;
consumers are created per consumer-group by their callers (see
workers/kafka/consumers/) since each consumer owns its own poll loop and
shutdown lifecycle.
"""
import logging
import time

from confluent_kafka import Consumer, KafkaException, Producer
from confluent_kafka.admin import AdminClient

from app.core.config import settings

logger = logging.getLogger(__name__)


def _producer_config() -> dict:
    return {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "client.id": settings.KAFKA_CLIENT_ID,
        "security.protocol": settings.KAFKA_SECURITY_PROTOCOL,
        "acks": settings.KAFKA_PRODUCER_ACKS,
        "enable.idempotence": True,  # no duplicate/out-of-order writes on retry
        "linger.ms": settings.KAFKA_PRODUCER_LINGER_MS,
        "retries": settings.KAFKA_PRODUCER_MAX_RETRIES,
        "delivery.timeout.ms": settings.KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS,
    }


def _consumer_config(group_id: str | None = None) -> dict:
    return {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "client.id": settings.KAFKA_CLIENT_ID,
        "security.protocol": settings.KAFKA_SECURITY_PROTOCOL,
        "group.id": group_id or settings.KAFKA_CONSUMER_GROUP_ID,
        "auto.offset.reset": settings.KAFKA_CONSUMER_AUTO_OFFSET_RESET,
        "enable.auto.commit": False,  # caller commits explicitly after successful processing
        "session.timeout.ms": settings.KAFKA_CONSUMER_SESSION_TIMEOUT_MS,
    }


_producer: Producer | None = None


def get_producer() -> Producer:
    """Process-wide singleton producer, created lazily on first use."""
    global _producer
    if _producer is None:
        _producer = Producer(_producer_config())
        logger.info("Kafka producer initialized (bootstrap=%s)", settings.KAFKA_BOOTSTRAP_SERVERS)
    return _producer


def _delivery_report(err, msg) -> None:  # noqa: ANN001 — confluent-kafka callback signature
    if err is not None:
        logger.error("Kafka delivery failed for topic=%s: %s", msg.topic(), err)
    else:
        logger.debug(
            "Kafka delivery succeeded: topic=%s partition=%s offset=%s",
            msg.topic(), msg.partition(), msg.offset(),
        )


def produce(topic: str, value: bytes | str, key: bytes | str | None = None) -> None:
    """
    Send a message asynchronously. Non-blocking; delivery success/failure is
    reported via `_delivery_report` the next time `poll()`/`flush()` runs.
    Pass a stable `key` when messages for the same logical entity must stay
    ordered (Kafka only guarantees order within a partition).
    """
    producer = get_producer()
    producer.produce(topic, value=value, key=key, on_delivery=_delivery_report)
    producer.poll(0)  # serve queued delivery-report callbacks without blocking


def create_consumer(topics: list[str], group_id: str | None = None) -> Consumer:
    """
    Build and subscribe a new Consumer. The caller owns the returned
    consumer's lifecycle: poll in a loop, commit offsets after successful
    processing, and call `close_consumer` on shutdown for a clean group
    rebalance instead of waiting out the session timeout.
    """
    consumer = Consumer(_consumer_config(group_id))
    consumer.subscribe(topics)
    return consumer


def close_consumer(consumer: Consumer) -> None:
    """Leave the consumer group cleanly and commit final offsets."""
    try:
        consumer.close()
    except KafkaException as e:
        logger.warning("Error while closing Kafka consumer: %s", e)


def check_kafka_connection(timeout: float = 5.0) -> bool:
    """Lightweight broker-reachability check via a cluster metadata lookup."""
    try:
        admin = AdminClient({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})
        cluster = admin.list_topics(timeout=timeout)
        return bool(cluster.brokers)
    except KafkaException as e:
        logger.error("Kafka health check failed: %s", e)
        return False


def check_kafka_connection_verbose(timeout: float = 5.0) -> dict:
    """Health check with latency and cluster stats, for a `/health/kafka` endpoint."""
    start = time.monotonic()
    try:
        admin = AdminClient({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})
        cluster = admin.list_topics(timeout=timeout)
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "brokers": len(cluster.brokers),
            "topics": len(cluster.topics),
        }
    except KafkaException as e:
        return {"status": "error", "detail": str(e)}


def connect_with_retry() -> None:
    """
    Blocking Kafka connectivity check with exponential backoff, meant to be
    called once at application startup.

    Like Redis, Kafka is treated as a soft dependency: event publishing
    degrades gracefully if the broker is temporarily unreachable, rather
    than crash-looping the whole API. PostgreSQL remains the only hard
    startup gate. Real-time status stays visible via `/health/kafka`.
    """
    max_retries = settings.KAFKA_STARTUP_MAX_RETRIES
    delay = settings.KAFKA_STARTUP_RETRY_BASE_DELAY

    for attempt in range(1, max_retries + 1):
        if check_kafka_connection():
            logger.info("Kafka connection established (attempt %d/%d)", attempt, max_retries)
            return
        if attempt == max_retries:
            logger.error(
                "Kafka connection failed after %d attempts — starting in degraded mode",
                max_retries,
            )
            return
        logger.warning(
            "Kafka connection attempt %d/%d failed — retrying in %.1fs",
            attempt, max_retries, delay,
        )
        time.sleep(delay)
        delay *= 2  # exponential backoff


def dispose_kafka() -> None:
    """Flush any in-flight messages and release the producer. Call on shutdown."""
    global _producer
    if _producer is not None:
        remaining = _producer.flush(timeout=10)
        if remaining > 0:
            logger.warning(
                "Kafka producer shutdown: %d message(s) were not delivered in time", remaining
            )
        _producer = None
        logger.info("Kafka producer disposed")
