"""Claude Vision analysis for Grafana dashboards and Kubernetes architecture diagrams."""
import anthropic
import base64
import httpx
import json
import logging
import os
import re

log = logging.getLogger("aois.vision")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_GRAFANA_PROMPT = """You are an SRE analyzing a Grafana dashboard screenshot.
Identify all anomalies, spikes, drops, and correlations visible in the graphs.
For each anomaly: note the time, metric name, and magnitude.
Return JSON:
{
  "anomalies": [{"metric": "...", "time": "...", "description": "..."}],
  "severity": "P1|P2|P3|P4",
  "hypothesis": "one-sentence root cause hypothesis",
  "recommended_investigation": "next kubectl command to run"
}"""

_ARCHITECTURE_PROMPT = """You are an SRE analyzing a Kubernetes architecture diagram.
Identify: service dependencies, single points of failure, which services share nodes.
Given the failure context provided, determine blast radius.
Return JSON:
{
  "affected_services": ["..."],
  "blast_radius": "description",
  "single_points_of_failure": ["..."],
  "recommended_action": "..."
}"""


def _call_vision(image_b64: str, media_type: str, prompt: str) -> str:
    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return response.content[0].text


def analyze_grafana_screenshot(image_b64: str, media_type: str = "image/png") -> dict:
    text = _call_vision(image_b64, media_type, _GRAFANA_PROMPT)
    try:
        return json.loads(re.search(r'\{.*\}', text, re.DOTALL).group())
    except Exception:
        return {"raw_analysis": text, "severity": "P3", "hypothesis": "Manual review required"}


def analyze_architecture_diagram(image_b64: str, failure_context: str,
                                  media_type: str = "image/png") -> dict:
    prompt = f"{_ARCHITECTURE_PROMPT}\n\nFailure context: {failure_context}"
    text = _call_vision(image_b64, media_type, prompt)
    try:
        return json.loads(re.search(r'\{.*\}', text, re.DOTALL).group())
    except Exception:
        return {"raw_analysis": text, "blast_radius": "unknown"}


def analyze_image_from_path(image_path: str, question: str) -> str:
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")
    ext = image_path.lower().rsplit(".", 1)[-1]
    media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                  "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
    return _call_vision(image_data, media_type, question)


def analyze_image_from_url(url: str, question: str) -> str:
    response = httpx.get(url, timeout=30)
    image_data = base64.standard_b64encode(response.content).decode("utf-8")
    media_type = response.headers.get("content-type", "image/png").split(";")[0]
    return _call_vision(image_data, media_type, question)


def resize_for_vision(image_bytes: bytes, max_width: int = 1568) -> bytes:
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return image_bytes
