"""Temporal worker — runs investigation workflows and activities."""
import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from temporal_workflows.activities import (
    describe_node_activity,
    get_metrics_activity,
    get_pod_logs_activity,
    list_events_activity,
    run_llm_step_activity,
    search_past_incidents_activity,
)
from temporal_workflows.investigation_workflow import InvestigationWorkflow

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("temporal_worker")

TASK_QUEUE = "aois-investigation"


async def main() -> None:
    client = await Client.connect(os.getenv("TEMPORAL_HOST", "localhost:7233"))
    log.info("Connected to Temporal at %s", os.getenv("TEMPORAL_HOST", "localhost:7233"))

    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[InvestigationWorkflow],
        activities=[
            get_pod_logs_activity,
            describe_node_activity,
            list_events_activity,
            get_metrics_activity,
            search_past_incidents_activity,
            run_llm_step_activity,
        ],
    ):
        log.info("Worker running on queue: %s", TASK_QUEUE)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
