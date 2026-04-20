"""
AOIS Kafka log producer — simulates infrastructure emitting log events.

Publishes realistic SRE log events to the `aois-logs` topic at a
configurable rate. Use this to generate load for testing the consumer
and observing KEDA scale-up behavior.

Usage:
    python3 kafka/producer.py                    # 1 msg/sec, continuous
    python3 kafka/producer.py --rate 10          # 10 msg/sec burst
    python3 kafka/producer.py --count 100        # exactly 100 messages then exit
    python3 kafka/producer.py --rate 50 --count 500  # backlog test
"""

import argparse
import json
import os
import random
import time
import uuid
from dotenv import load_dotenv

load_dotenv()

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
INPUT_TOPIC = "aois-logs"

# Realistic SRE log samples — same categories as the fine-tuning dataset
SAMPLE_LOGS = [
    # OOM / Memory — P1/P2
    "OOMKilled: container aois-api exceeded memory limit 512Mi, exit code 137",
    "pod/worker-{n}d9f killed: memory limit exceeded, used 1.8Gi of 1Gi limit",
    "Java heap space OutOfMemoryError in payment-service, GC overhead limit exceeded",
    "Node memory pressure detected: available 128Mi of 8Gi, evicting pods",
    # CrashLoop — P1/P2
    "CrashLoopBackOff: auth-service failed {n} times in 10 minutes, last exit code 1",
    "Back-off restarting failed container nginx-proxy in pod ingress-7f8d, restarts: {n}",
    # Disk — P2/P3
    "Disk usage at {n}% on /var/lib/docker, inode exhaustion imminent",
    "PersistentVolumeClaim postgres-data: {n}% full, 512Mi remaining of 10Gi",
    "No space left on device: /var/log partition full, log rotation failed",
    # Network / DNS — P2/P3
    "DNS resolution failed for redis.prod.svc.cluster.local: timeout after 5s",
    "Connection refused: postgres:5432, pod api-server retrying (attempt {n})",
    "Service mesh timeout: auth → payment latency p99={n}ms, threshold=3000ms",
    # TLS — P2/P3
    "TLS certificate for api.prod.company.com expires in {n} days",
    "cert-manager: CertificateRequest failed: ACME challenge DNS01 timed out",
    # 5xx spikes — P1/P2
    "HTTP 503 rate: {n}% of requests, upstream payment-service unhealthy",
    "Error rate spike: 500 errors increased from 0.1% to {n}% in last 5 minutes",
    # CPU — P2/P3
    "CPU throttling: container api-server throttled {n}% of the time, limit 500m",
    "HPA unable to scale: CPU utilization {n}%, max replicas 10 already reached",
    # Kubernetes — P1/P2
    "Node worker-{n} NotReady: kubelet stopped posting node status, last heartbeat 8m ago",
    "Deployment rollout stuck: {n}/5 pods ready, readiness probe failing on /healthz",
    "ImagePullBackOff: ghcr.io/org/api:v2.1.0 not found or no pull credentials",
    # Database — P1/P2/P3
    "PostgreSQL: max_connections reached ({n}/100), new connections being rejected",
    "Slow query alert: SELECT * FROM events WHERE timestamp > NOW() - INTERVAL '1 day' took {n}s",
    "Replication lag: replica-2 is {n}GB behind primary, catching up",
    "Deadlock detected in transaction on table orders, rolled back",
    "Redis: used_memory {n}GB of 8GB maxmemory, evicting keys with allkeys-lru",
    # Security — P1/P2
    "Failed login attempts: {n} failures for user admin from IP 185.220.101.x in 1 hour",
    "Falco alert: unexpected outbound connection from pod api-server to 1.2.3.4:4444",
    # Kafka — P2/P3
    "Consumer lag: topic aois-logs partition 0 lag={n}, consumer group aois-workers",
    "Kafka broker disk {n}% full: /kafka/data, oldest offset retention at risk",
    "Producer timeout: unable to publish to topic events after 3 retries, broker unavailable",
]


def vary(template: str) -> str:
    """Replace {n} placeholders with realistic random values."""
    import re
    def _rand(m):
        return str(random.choice([2, 5, 8, 12, 14, 23, 45, 67, 78, 94, 95, 97, 142000]))
    return re.sub(r'\{n\}', _rand, template)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate", type=float, default=1.0, help="Messages per second")
    parser.add_argument("--count", type=int, default=0, help="Total messages (0=unlimited)")
    parser.add_argument("--bootstrap", default=BOOTSTRAP_SERVERS)
    args = parser.parse_args()

    from kafka import KafkaProducer
    from kafka.errors import NoBrokersAvailable

    for attempt in range(12):
        try:
            producer = KafkaProducer(
                bootstrap_servers=args.bootstrap,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                api_version=(3, 7, 0),
            )
            print(f"Connected to Kafka at {args.bootstrap}")
            break
        except NoBrokersAvailable:
            print(f"Kafka not ready ({attempt+1}/12), retrying in 5s...")
            time.sleep(5)
    else:
        print("Could not connect to Kafka — is the broker running?")
        print(f"  docker compose up -d kafka")
        raise SystemExit(1)

    delay = 1.0 / args.rate
    sent = 0

    print(f"Publishing to '{INPUT_TOPIC}' at {args.rate:.1f} msg/sec"
          + (f", total {args.count}" if args.count else ", press Ctrl+C to stop"))

    try:
        while True:
            log = vary(random.choice(SAMPLE_LOGS))
            event = {
                "id": str(uuid.uuid4())[:8],
                "log": log,
                "source": "aois-producer",
                "ts": time.time(),
            }
            producer.send(INPUT_TOPIC, value=event)
            sent += 1

            if sent % 10 == 0:
                print(f"  Sent {sent} messages | last: {log[:70]}...")

            if args.count and sent >= args.count:
                break

            time.sleep(delay)

    except KeyboardInterrupt:
        pass

    producer.flush()
    print(f"\nDone. Sent {sent} messages to '{INPUT_TOPIC}'.")


if __name__ == "__main__":
    main()
