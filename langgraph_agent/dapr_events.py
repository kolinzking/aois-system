"""
Publish graph node events to Dapr pub/sub.
Subscribers (logging, monitoring, notifications) receive these without
any changes to the graph itself.
"""
from dapr.clients import DaprClient
import json
import logging

log = logging.getLogger("dapr_events")
_PUBSUB_NAME = "pubsub"  # Dapr component name (Redis by default in local init)
_TOPIC = "aois-investigation-events"


def publish_node_event(node_name: str, session_id: str, data: dict) -> None:
    """Publish a node completion event to Dapr pub/sub."""
    event = {
        "node": node_name,
        "session_id": session_id,
        "data": data,
    }
    try:
        with DaprClient() as d:
            d.publish_event(
                pubsub_name=_PUBSUB_NAME,
                topic_name=_TOPIC,
                data=json.dumps(event),
                data_content_type="application/json",
            )
        log.info("Published %s event for session %s", node_name, session_id)
    except Exception as e:
        log.warning("Dapr publish failed (non-fatal): %s", e)
