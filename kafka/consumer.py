"""
AOIS Kafka consumer worker.

Consumes SRE log events from `aois-logs`, runs analyze(), publishes
structured results to `aois-results`.

Usage (local):
    python3 kafka/consumer.py

Usage (container):
    Set KAFKA_BOOTSTRAP_SERVERS, ANTHROPIC_API_KEY, GROQ_API_KEY in env.
    Runs as a long-lived process alongside the FastAPI server (or separately).
"""

import json
import os
import sys
import time
import signal
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    level=logging.INFO,
)
logger = logging.getLogger("aois.kafka")

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
INPUT_TOPIC = "aois-logs"
OUTPUT_TOPIC = "aois-results"
CONSUMER_GROUP = "aois-workers"


def get_tier_for_log(log: str) -> str:
    """Quick pre-filter: use fast tier unless log screams P1."""
    p1_keywords = ["OOMKilled", "CrashLoop", "NotReady", "production down", "data loss", "503"]
    if any(kw.lower() in log.lower() for kw in p1_keywords):
        return "premium"
    return "fast"


def run():
    from kafka import KafkaConsumer, KafkaProducer
    from kafka.errors import NoBrokersAvailable

    # Import analyze from the AOIS app — same logic, same routing
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from main import analyze

    # Retry connection — broker may not be ready immediately on startup
    for attempt in range(12):
        try:
            consumer = KafkaConsumer(
                INPUT_TOPIC,
                bootstrap_servers=BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda b: json.loads(b.decode("utf-8")),
                consumer_timeout_ms=1000,
            )
            producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            logger.info(f"Connected to Kafka at {BOOTSTRAP_SERVERS}")
            break
        except NoBrokersAvailable:
            logger.warning(f"Kafka not ready (attempt {attempt+1}/12), retrying in 5s...")
            time.sleep(5)
    else:
        logger.error("Could not connect to Kafka after 60s — exiting")
        sys.exit(1)

    # Graceful shutdown
    running = True
    def _stop(sig, frame):
        nonlocal running
        logger.info("Shutting down consumer...")
        running = False
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info(f"Consuming from '{INPUT_TOPIC}' → publishing to '{OUTPUT_TOPIC}'")
    processed = 0

    while running:
        for message in consumer:
            if not running:
                break

            event = message.value
            log_text = event.get("log", "")
            event_id = event.get("id", f"msg-{message.offset}")
            tier = event.get("tier") or get_tier_for_log(log_text)

            t0 = time.perf_counter()
            try:
                result = analyze(log_text, tier)
                duration_ms = (time.perf_counter() - t0) * 1000

                output = {
                    "id": event_id,
                    "log": log_text,
                    "tier": tier,
                    "summary": result.summary,
                    "severity": result.severity,
                    "suggested_action": result.suggested_action,
                    "confidence": result.confidence,
                    "provider": result.provider,
                    "cost_usd": result.cost_usd,
                    "duration_ms": round(duration_ms, 1),
                    "kafka_offset": message.offset,
                    "kafka_partition": message.partition,
                }

                producer.send(OUTPUT_TOPIC, value=output)
                processed += 1

                logger.info(
                    f"[{event_id}] {result.severity} — {result.summary[:60]} "
                    f"({tier}, {duration_ms:.0f}ms, ${result.cost_usd:.6f})"
                )

            except Exception as e:
                logger.error(f"[{event_id}] Analysis failed: {e}")
                # Publish error event so downstream knows this message was attempted
                producer.send(OUTPUT_TOPIC, value={
                    "id": event_id,
                    "log": log_text,
                    "error": str(e),
                    "kafka_offset": message.offset,
                })

        # consumer_timeout_ms fires every 1s when no messages — keeps the while loop alive

    producer.flush()
    consumer.close()
    logger.info(f"Consumer stopped. Processed {processed} messages.")


if __name__ == "__main__":
    run()
