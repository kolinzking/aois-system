"""Seed 10 synthetic SRE incidents into pgvector for v3.5 RAG exercises."""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from pgvector_store import index_incident

load_dotenv()

INCIDENTS = [
    ("INC-001", "pod OOMKilled exit code 137 auth-service",               "P2",
     "Increased memory limit from 512Mi to 768Mi", "JWT cache unbounded growth"),
    ("INC-002", "CrashLoopBackOff api-gateway ImagePullBackOff",          "P3",
     "Fixed image tag from :latest to :v1.2.3",    "Unstable latest tag"),
    ("INC-003", "disk pressure node-1 /var/lib/kubelet 95% full",         "P2",
     "Pruned old container images with crictl rmi", "Docker images accumulated"),
    ("INC-004", "5xx spike 503 upstream connect error or disconnect",     "P1",
     "Rolled back deployment to v2.1.0",            "Memory leak in v2.2.0"),
    ("INC-005", "certificate expired for aois.example.com",               "P2",
     "Renewed via cert-manager ACME challenge",     "cert-manager misconfigured renewal"),
    ("INC-006", "pod OOMKilled payment-service exit code 137",            "P2",
     "Increased memory limit from 1Gi to 2Gi",      "Burst traffic during sale"),
    ("INC-007", "Kafka consumer lag growing aois-logs partition 0",       "P3",
     "Scaled consumer pods from 1 to 3",            "KEDA threshold set too high"),
    ("INC-008", "CPU throttling 99% on analysis-worker pods",             "P3",
     "Raised CPU limit from 500m to 1000m",         "Batch job competed with realtime"),
    ("INC-009", "etcd high latency 500ms p99 disk io wait",               "P1",
     "Moved etcd data to NVMe volume",              "Spinning disk caused election timeouts"),
    ("INC-010", "auth-service memory spike RSS 900Mi out of 512Mi limit", "P2",
     "Increased limit and added memory profiling",  "Session store not evicting expired sessions"),
]


async def main() -> None:
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    for inc_id, log, sev, resolution, root_cause in INCIDENTS:
        await index_incident(db, inc_id, log, sev, resolution, root_cause)
        print(f"Indexed {inc_id}: {log[:55]}")
    await db.close()
    print("Done — 10 incidents indexed.")


if __name__ == "__main__":
    asyncio.run(main())
