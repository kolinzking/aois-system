# v31 — Multimodal AOIS: Claude Vision for Dashboard Analysis

⏱ **Estimated time: 4–5 hours**

---

## Prerequisites

v30 IDP complete. AOIS FastAPI running. Anthropic API key with claude-sonnet-4-6 access.

```bash
python3 -c "import anthropic, base64; print('ok')"
# ok

# Test vision API access
python3 - << 'EOF'
import anthropic, base64, os
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=64,
    messages=[{"role":"user","content":[
        {"type":"image","source":{"type":"base64","media_type":"image/png",
         "data": base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00'*16).decode()}},
        {"type":"text","text":"What is this?"}
    ]}]
)
print("Vision ok:", resp.content[0].text[:40])
EOF
```

---

## Learning Goals

By the end you will be able to:

- Pass a Grafana dashboard screenshot to Claude Vision and extract anomaly descriptions
- Analyze a Kubernetes architecture diagram and identify potential blast radius of a failure
- Build the AOIS `/analyze/image` endpoint that accepts base64 or URL images
- Explain the multimodal prompt pattern: image + structured text instruction = structured output
- Identify the cost and latency difference between vision calls and text-only calls

---

## The Problem

AOIS ingests text logs. But an on-call engineer staring at a Grafana dashboard sees spikes, drops, and correlations that are invisible in raw log text. A dashboard screenshot contains information that is not in any single log line:

- The latency percentile fan-out at 03:42 that preceded the OOMKill
- The correlation between Redis eviction rate and API error rate
- The topology diagram showing which services share a node

Claude Vision reads images. AOIS can now receive a screenshot and produce: "I can see from this dashboard that p99 latency began climbing at 03:38, four minutes before the OOMKill alert. The Redis eviction counter jumped simultaneously — this suggests the auth-service is allocating cache objects that Redis is evicting, causing recomputation that exhausts memory."

---

## The Vision API Pattern

```python
import anthropic
import base64
import httpx
import os

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def analyze_image_from_path(image_path: str, question: str) -> str:
    """Analyze a local image file."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    media_type = "image/png" if image_path.endswith(".png") else "image/jpeg"

    response = client.messages.create(
        model="claude-sonnet-4-6",  # Vision requires Sonnet or Opus — not Haiku
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": question,
                },
            ],
        }],
    )
    return response.content[0].text


def analyze_image_from_url(url: str, question: str) -> str:
    """Fetch and analyze an image from a URL."""
    response = httpx.get(url)
    image_data = base64.standard_b64encode(response.content).decode("utf-8")
    media_type = response.headers.get("content-type", "image/png").split(";")[0]

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": question},
            ],
        }],
    )
    return resp.content[0].text
```

---

## ▶ STOP — do this now

Take a screenshot of the Grafana dashboard (or use any Grafana screenshot you have). Run:

```python
from multimodal.vision import analyze_image_from_path

result = analyze_image_from_path(
    "grafana_screenshot.png",
    """You are an SRE analyzing this Grafana dashboard.
    Identify: 1) Any anomalies or spikes visible in the graphs.
    2) Time range of anomalies.
    3) Which metrics correlate with each other.
    Return JSON: {"anomalies": [...], "severity": "P1-P4", "hypothesis": "..."}"""
)
print(result)
```

If you do not have a Grafana screenshot, generate a test image:

```python
# Create a minimal test PNG (red 1x1 pixel)
import struct, zlib, base64

def make_test_png(color=(255, 0, 0)):
    def chunk(name, data):
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c))
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    row = b'\x00' + bytes(color)
    idat = zlib.compress(row)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')

with open('/tmp/test.png', 'wb') as f:
    f.write(make_test_png())

result = analyze_image_from_path('/tmp/test.png', 'Describe this image in one sentence.')
print(result)
# Expected: "This image shows a single red pixel."
```

---

## The AOIS Multimodal Endpoint

```python
# multimodal/vision.py — full module
"""Claude Vision analysis for Grafana dashboards and architecture diagrams."""
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
```

---

## FastAPI Endpoint

```python
# Add to main.py
from fastapi import UploadFile, File, Form
from multimodal.vision import analyze_grafana_screenshot, analyze_architecture_diagram
import base64


@app.post("/analyze/image")
async def analyze_image_endpoint(
    file: UploadFile = File(...),
    image_type: str = Form("grafana"),
    context: str = Form(""),
):
    """
    Analyze a Grafana screenshot or architecture diagram.
    image_type: 'grafana' | 'architecture'
    """
    content = await file.read()
    image_b64 = base64.standard_b64encode(content).decode("utf-8")
    media_type = file.content_type or "image/png"

    if image_type == "architecture":
        result = analyze_architecture_diagram(image_b64, context, media_type)
    else:
        result = analyze_grafana_screenshot(image_b64, media_type)

    return result
```

Test:
```bash
curl -X POST http://localhost:8000/analyze/image \
  -F "file=@grafana_screenshot.png" \
  -F "image_type=grafana" | jq .
```

---

## ▶ STOP — do this now

Test the full endpoint with a real Grafana screenshot. Confirm the response includes `severity`, `hypothesis`, and at least one `anomaly`. Record the latency and cost:

```bash
time curl -X POST http://localhost:8000/analyze/image \
  -F "file=@grafana_screenshot.png" -F "image_type=grafana"
```

Expected latency: 3–8 seconds (Sonnet with vision is slower than Haiku text-only).
Expected cost: ~$0.005–$0.02 depending on image size (vision tokens are more expensive).

This is the cost-quality tradeoff: vision calls are 10–50× more expensive than text calls. Use them for dashboard analysis only when the image contains information not in any log line.

---

## Common Mistakes

### 1. Using Haiku for vision — model does not support it

```python
# Wrong — Haiku does not have vision
model="claude-haiku-4-5-20251001"

# Correct — Sonnet or Opus for vision
model="claude-sonnet-4-6"
```

Vision capability is only available on Sonnet and Opus tier models. Haiku calls with image content return a 400 error.

### 2. Image too large — exceeds token limit

Grafana screenshots at full resolution can be 2–4MB. Claude Vision accepts images up to 5MB, but very large images consume many tokens. Resize before sending:

```python
from PIL import Image
import io

def resize_for_vision(image_bytes: bytes, max_width: int = 1568) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

---

## Troubleshooting

### `anthropic.BadRequestError: Could not process image`

The image encoding is wrong. Verify:
```python
# The base64 string must not contain line breaks
image_b64 = base64.standard_b64encode(content).decode("utf-8")
# Not: base64.encodebytes() which adds newlines
```

### Vision response is "I cannot analyze this image"

The image is too small, blurry, or contains no recognizable structure. For test images: use a real Grafana screenshot, not a generated test PNG.

---

## Connection to Later Phases

### To v34 (Computer Use): vision identifies the anomaly; computer use navigates the Grafana UI to drill down without a screenshot — full UI interaction.
### To v34.5 (Capstone): during the game day, the operator can upload a dashboard screenshot and AOIS provides a vision-enhanced hypothesis alongside the text-log analysis.

---

## Mastery Checkpoint

1. Run `analyze_image_from_path` on any screenshot. Show the raw Claude Vision response.
2. Call the `/analyze/image` endpoint with a Grafana screenshot. Show the JSON response including severity and hypothesis.
3. Measure and record the latency and estimated cost of a single vision call. Compare to a text-only `/analyze` call with the same incident description.
4. Explain why `claude-sonnet-4-6` is used instead of `claude-haiku-4-5-20251001` for vision. What is the quality difference and the cost difference?
5. An operator uploads a k8s architecture diagram when auth-service is OOMKilling. What is the specific question you would pass to `analyze_architecture_diagram`? Write the `failure_context` string.
6. Explain to a product manager: what information does a Grafana dashboard contain that text logs do not? Give one concrete example from an incident you have seen.

**The mastery bar:** you can submit a Grafana screenshot to AOIS and receive a structured analysis including severity classification, anomaly timeline, and root cause hypothesis — all from the visual content of the image.

---

## 4-Layer Tool Understanding

### Claude Vision (Multimodal)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | An on-call engineer sees a spike on a Grafana dashboard that is not in any log file — it is in the shape of the graph. Claude Vision reads the image and describes what it sees: "latency began climbing at 03:38, four minutes before the alert fired." Text logs cannot tell you what happened four minutes before the alert. |
| **System Role** | Where does it sit in AOIS? | An additional input channel alongside text logs. The `/analyze/image` endpoint accepts screenshots. The vision analysis produces the same structured output (severity, hypothesis, recommended_action) that text analysis produces — AOIS handles both input types uniformly. |
| **Technical** | What is it precisely? | The Anthropic API's multimodal capability: image content blocks alongside text content blocks in the `messages` array. Images are base64-encoded. The model processes visual tokens (charged at a higher rate than text tokens). Only Sonnet and Opus support vision. Response is standard text/JSON from the model. |
| **Remove it** | What breaks, and how fast? | Remove vision → AOIS is text-only. Dashboard screenshots cannot be analyzed. Architectural diagrams cannot be interpreted. An operator who screenshots a Grafana anomaly at 3am and asks AOIS "what is wrong?" gets "I cannot analyze images." The operator's fastest available diagnostic tool is cut off from AOIS's analysis capability. |
