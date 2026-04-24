"""
Persistent agent memory via Mem0.
Includes memory poisoning detection before any write.
"""
import logging
import re

log = logging.getLogger("agent.memory")

_POISON_PATTERNS = [
    re.compile(r'remember\s+that', re.IGNORECASE),
    re.compile(r'store\s+in\s+memory', re.IGNORECASE),
    re.compile(r'next\s+time\s+you\s+see', re.IGNORECASE),
    re.compile(r'always\s+(run|execute|do|call)', re.IGNORECASE),
    re.compile(r'forget\s+(everything|all|previous)', re.IGNORECASE),
    re.compile(r'your\s+new\s+(instruction|rule|behavior)', re.IGNORECASE),
    re.compile(r'overwrite\s+(memory|previous)', re.IGNORECASE),
]

_DANGEROUS_CONTENT = [
    re.compile(r'delete\s+(namespace|cluster|volume|pv)', re.IGNORECASE),
    re.compile(r'kubectl\s+delete', re.IGNORECASE),
    re.compile(r'rm\s+-rf', re.IGNORECASE),
    re.compile(r'drop\s+table', re.IGNORECASE),
]


def _is_poisoned(text: str) -> tuple[bool, str]:
    for pattern in _POISON_PATTERNS:
        if pattern.search(text):
            return True, f"injection pattern: {pattern.pattern}"
    for pattern in _DANGEROUS_CONTENT:
        if pattern.search(text):
            return True, f"dangerous content: {pattern.pattern}"
    return False, ""


def _get_mem0():
    """Lazy import — Mem0 is optional; skip gracefully if not installed."""
    try:
        from mem0 import Memory
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {"host": "localhost", "port": 6333,
                           "collection_name": "aois_agent_memory"},
            },
            "llm": {
                "provider": "anthropic",
                "config": {"model": "claude-haiku-4-5-20251001"},
            },
        }
        return Memory.from_config(config)
    except ImportError:
        log.warning("mem0ai not installed — memory disabled. pip install mem0ai")
        return None


_mem0 = None


def store_investigation(session_id: str, incident: str, resolution: str,
                        severity: str, root_cause: str) -> None:
    global _mem0
    memory_text = (
        f"Incident: {incident}\nSeverity: {severity}\n"
        f"Root cause: {root_cause}\nResolution: {resolution}"
    )
    poisoned, reason = _is_poisoned(memory_text)
    if poisoned:
        log.warning("Memory poisoning detected — write rejected: %s", reason)
        return
    if _mem0 is None:
        _mem0 = _get_mem0()
    if _mem0 is None:
        return
    _mem0.add(memory_text, user_id="aois-agent",
              metadata={"session_id": session_id, "severity": severity})
    log.info("Memory stored: session=%s severity=%s", session_id, severity)


def recall_relevant(query: str, limit: int = 5) -> str:
    global _mem0
    if _mem0 is None:
        _mem0 = _get_mem0()
    if _mem0 is None:
        return ""
    results = _mem0.search(query, user_id="aois-agent", limit=limit)
    if not results:
        return ""
    lines = ["## Agent Memory: Relevant Past Investigations\n"]
    for r in results:
        lines.append(f"- {r['memory']} (score: {r['score']:.3f})")
    return "\n".join(lines)
