"""
AOIS investigation as a Temporal workflow.
Durable: survives pod restarts, crashes, and deployments.
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from temporal_workflows.activities import (
    describe_node_activity,
    get_metrics_activity,
    get_pod_logs_activity,
    list_events_activity,
    run_llm_step_activity,
    search_past_incidents_activity,
)

_ACTIVITY_OPTIONS = dict(
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=1),
        maximum_interval=timedelta(seconds=10),
        maximum_attempts=3,
        non_retryable_error_types=["ToolBlocked"],
    ),
    heartbeat_timeout=timedelta(seconds=10),
)

AGENT_SYSTEM_PROMPT = (
    "You are AOIS, an autonomous SRE investigation agent. "
    "Always search past incidents first. Investigate with tools, then provide: "
    "Severity (P1-P4), Root cause, Evidence summary, Recommended action."
)

_TOOL_ACTIVITY_MAP = {
    "get_pod_logs":          get_pod_logs_activity,
    "describe_node":         describe_node_activity,
    "list_events":           list_events_activity,
    "get_metrics":           get_metrics_activity,
    "search_past_incidents": search_past_incidents_activity,
}


@workflow.defn(name="InvestigationWorkflow")
class InvestigationWorkflow:

    @workflow.run
    async def run(self, incident: str, session_id: str,
                  agent_role: str = "read_only") -> dict:
        workflow.logger.info("Investigation started: %s", incident[:80])

        messages = [{"role": "user", "content": incident}]
        tool_calls_made: list[dict] = []
        total_input = total_output = 0

        for iteration in range(10):
            llm_result = await workflow.execute_activity(
                run_llm_step_activity,
                args=[messages, AGENT_SYSTEM_PROMPT],
                **_ACTIVITY_OPTIONS,
            )
            total_input  += llm_result["usage"]["input_tokens"]
            total_output += llm_result["usage"]["output_tokens"]

            if llm_result["stop_reason"] == "end_turn":
                final_text = next(
                    (b["text"] for b in llm_result["content"] if b.get("type") == "text"), ""
                )
                cost_usd = (total_input * 0.80 + total_output * 4.00) / 1_000_000
                return {
                    "session_id": session_id,
                    "incident": incident,
                    "investigation": final_text,
                    "tool_calls": tool_calls_made,
                    "iterations": iteration + 1,
                    "cost_usd": round(cost_usd, 6),
                    "total_input_tokens": total_input,
                    "total_output_tokens": total_output,
                }

            messages.append({"role": "assistant", "content": llm_result["content"]})
            tool_results = []

            for block in llm_result["content"]:
                if block.get("type") != "tool_use":
                    continue
                tool_name  = block["name"]
                tool_input = block["input"]
                tool_calls_made.append({"tool": tool_name, "input": tool_input})

                activity_fn = _TOOL_ACTIVITY_MAP.get(tool_name)
                if activity_fn is None:
                    result_text = f"Unknown tool: {tool_name}"
                else:
                    try:
                        result_text = await workflow.execute_activity(
                            activity_fn,
                            kwargs={**tool_input, "session_id": session_id},
                            **_ACTIVITY_OPTIONS,
                        )
                    except Exception as e:
                        result_text = f"[Tool error: {e}]"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": str(result_text)[:4000],
                })

            messages.append({"role": "user", "content": tool_results})

        return {
            "session_id": session_id,
            "incident": incident,
            "investigation": "Max iterations reached",
            "tool_calls": tool_calls_made,
            "error": "max_iterations_exceeded",
        }
