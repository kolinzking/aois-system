# v31 — Multimodal AOIS: Claude Vision for Dashboard Analysis

⏱ **Estimated time: 4–5 hours**

---

## Prerequisites

v30 IDP complete. AOIS FastAPI running. Anthropic API key with claude-sonnet-4-6 access.

```bash
python3 -c "import anthropic, base64; print('ok')"
# ok

# Verify vision API access — send a minimal PNG to confirm model accepts images
python3 - << 'EOF'
import anthropic, base64, os
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Minimal valid 1x1 red PNG
import struct, zlib
def make_png():
    def chunk(name, data):
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c))
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    row = b'\x00' + bytes([255, 0, 0])
    idat = zlib.compress(row)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')

img_b64 = base64.standard_b64encode(make_png()).decode()
resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=64,
    messages=[{"role":"user","content":[
        {"type":"image","source":{"type":"base64","media_type":"image/png","data": img_b64}},
        {"type":"text","text":"Describe this image in one sentence."}
    ]}]
)
print("Vision ok:", resp.content[0].text[:60])
EOF
# Vision ok: This image shows a single red pixel...
```

If the vision call fails with `400 Bad Request`, verify your API key has Sonnet access. Haiku does not support vision.

---

## Learning Goals

By the end you will be able to:

- Pass a Grafana dashboard screenshot to Claude Vision and extract structured anomaly descriptions
- Analyze a Kubernetes architecture diagram and identify blast radius of a failure
- Build the AOIS `/analyze/image` FastAPI endpoint that accepts file uploads
- Explain why vision inputs cost more than text inputs, and when that cost is justified
- Identify the multimodal prompt pattern: image + structured text instruction → structured JSON output
- Resize images before sending to control token cost without losing diagnostic fidelity

---

## The Problem Vision Solves

AOIS ingests text logs. Every log line is one event: a timestamp, a pod name, an error code. But an on-call engineer staring at a Grafana dashboard at 3am sees information that does not exist in any single log line:

- The latency percentile fan-out that started 4 minutes before the OOMKill fired
- The correlation between Redis eviction rate climbing and API error rate climbing simultaneously
- The gap in the request rate metric that shows exactly when the pod went unresponsive
- The topology diagram showing that auth-service and payments-api share the same node — so a node failure affects both

This information lives in the shape of the graph, not in any individual log event. A text-only AOIS cannot see it.

Claude Vision reads the image and produces: *"I can see from this dashboard that p99 latency began climbing at 03:38, four minutes before the OOMKill alert. The Redis eviction counter jumped simultaneously — this suggests the auth-service is allocating cache objects that Redis is evicting, causing recomputation that exhausts memory."*

That hypothesis is built from visual pattern recognition across multiple time-series panels — not from any log event.

---

## How Claude Vision Works

Claude processes images as a sequence of visual tokens, similar to how it processes text tokens. An image is base64-encoded and sent as an `image` content block alongside a `text` content block. The model reasons across both.

Key constraints:
- **Supported formats**: JPEG, PNG, GIF, WebP
- **Maximum size**: 5MB per image
- **Maximum dimensions**: 8000 × 8000 pixels, but large images consume many tokens
- **Model support**: Sonnet and Opus only — Haiku does not support vision
- **Token cost**: vision tokens are more expensive than text tokens — a 1568px-wide screenshot costs roughly 1,600 tokens

The pricing formula: `image_tokens = (width × height) / 750`. A 1568×1080 Grafana screenshot ≈ 2,259 tokens before any text. This is why resizing matters.

---

## The Vision API Pattern

```python
# multimodal/vision.py
import anthropic
import base64
import httpx
import os

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def analyze_image_from_path(image_path: str, question: str) -> str:
    """Analyze a local image file with Claude Vision."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    ext = image_path.lower().rsplit(".", 1)[-1]
    media_type = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }.get(ext, "image/png")

    response = client.messages.create(
        model="claude-sonnet-4-6",   # Vision requires Sonnet or Opus — NOT Haiku
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
```

The structure is: `messages[0].content` is a list — image block first, text block second. The model receives both and reasons across them.

---

## ▶ STOP — do this now

Generate a test PNG and confirm Claude Vision works end-to-end:

```python
import struct, zlib, base64, anthropic, os

# Build a minimal valid PNG (1x1 red pixel)
def make_test_png(color=(255, 0, 0)):
    def chunk(name, data):
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c))
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    row = b'\x00' + bytes(color)
    idat = zlib.compress(row)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')

with open('/tmp/test_red.png', 'wb') as f:
    f.write(make_test_png((255, 0, 0)))

from multimodal.vision import analyze_image_from_path
result = analyze_image_from_path('/tmp/test_red.png', 'Describe this image in one sentence.')
print(result)
```

Expected output:
```
This image shows a single red pixel on a white or transparent background.
```

Now test with a real Grafana screenshot if you have one running. If not, use any PNG screenshot — even a terminal window screenshot will work to verify the endpoint before adding real dashboards.

---

## The Grafana Analysis Prompt

The multimodal prompt for Grafana analysis has two parts: the image (what Claude sees) and a structured instruction (what Claude should do with it). The instruction defines the output schema.

```python
_GRAFANA_PROMPT = """You are an SRE analyzing a Grafana dashboard screenshot.
Identify all anomalies, spikes, drops, and correlations visible in the graphs.
For each anomaly: note the approximate time visible on the x-axis, the metric name
from the panel title, and the magnitude (how far from baseline).

Look specifically for:
- Latency percentile divergence (p50 vs p99 separation widening)
- Error rate spikes coinciding with latency changes
- Resource metrics (CPU, memory, disk) approaching limits
- Correlation between panels — two metrics moving together suggests causation
- Gaps or flatlines in metrics (often means the service stopped responding)

Return JSON only — no text before or after:
{
  "anomalies": [
    {"metric": "panel name", "time": "approx time from x-axis", "description": "what changed and by how much"}
  ],
  "severity": "P1|P2|P3|P4",
  "hypothesis": "one-sentence root cause hypothesis connecting the anomalies",
  "recommended_investigation": "specific kubectl or Grafana action to confirm the hypothesis",
  "confidence": 0.0
}"""
```

The hypothesis is the key output — it synthesizes what individual log lines cannot. Each anomaly entry is a supporting data point.

---

## ▶ STOP — do this now

Take a screenshot of any running Grafana dashboard (or use any Grafana screenshot you have saved). Run:

```python
import json, re
from multimodal.vision import analyze_image_from_path

result = analyze_image_from_path(
    "grafana_screenshot.png",
    """You are an SRE analyzing this Grafana dashboard.
    Identify: 1) Any anomalies or spikes visible in the graphs.
    2) Time range of anomalies.
    3) Which metrics correlate with each other.
    Return JSON: {"anomalies": [...], "severity": "P1-P4", "hypothesis": "...", "confidence": 0.0}"""
)
print("Raw response:")
print(result[:500])

# Parse the JSON
try:
    data = json.loads(re.search(r'\{.*\}', result, re.DOTALL).group())
    print("\nSeverity:", data.get("severity"))
    print("Hypothesis:", data.get("hypothesis"))
    print("Anomalies found:", len(data.get("anomalies", [])))
except Exception as e:
    print("JSON parse failed:", e)
    print("Raw output:", result)
```

If you don't have a Grafana screenshot: use any chart-heavy image — a stock price chart, a Google Analytics screenshot, anything with time-series data. Claude Vision will identify whatever structure is present.

Expected structure:
```json
{
  "anomalies": [
    {"metric": "Request Duration", "time": "03:38", "description": "p99 climbed from 400ms to 8500ms"},
    {"metric": "Error Rate", "time": "03:42", "description": "spiked from 0.1% to 23%"}
  ],
  "severity": "P1",
  "hypothesis": "Latency degradation at 03:38 preceded error spike — suggests memory pressure causing GC pauses before OOMKill",
  "recommended_investigation": "kubectl describe pod auth-service-xxx -n production | grep -A5 OOMKilled",
  "confidence": 0.78
}
```

---

## Architecture Diagram Analysis

The same vision API works for Kubernetes topology diagrams. The prompt changes; the API call is identical.

```python
_ARCHITECTURE_PROMPT = """You are an SRE analyzing a Kubernetes architecture diagram.
Identify: service dependencies, which services share nodes, network paths, storage dependencies.

Given the failure context provided, determine:
- Which services are directly affected (same pod, same node, same dependency)
- Which services are indirectly affected (downstream consumers)
- Single points of failure visible in the diagram
- Whether the failure is likely to be contained or cascade

Return JSON:
{
  "affected_services": ["service names directly impacted"],
  "downstream_impact": ["services that will fail if affected_services go down"],
  "single_points_of_failure": ["components with no redundancy visible"],
  "blast_radius": "plain English description of impact scope",
  "recommended_action": "first mitigation step"
}"""


def analyze_architecture_diagram(image_b64: str, failure_context: str,
                                  media_type: str = "image/png") -> dict:
    prompt = f"{_ARCHITECTURE_PROMPT}\n\nFailure context: {failure_context}"
    text = _call_vision(image_b64, media_type, prompt)
    try:
        return json.loads(re.search(r'\{.*\}', text, re.DOTALL).group())
    except Exception:
        return {"raw_analysis": text, "blast_radius": "manual review required"}
```

When an operator submits a k8s architecture diagram during an auth-service OOMKill, the `failure_context` string is: `"auth-service OOMKilled in namespace production. Pod memory limit: 512Mi. Node: node-3."` Claude can then identify whether payments-api and auth-service share node-3 — meaning the node itself may be under memory pressure, not just one pod.

---

## The FastAPI Endpoint

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

    image_type: 'grafana' or 'architecture'
    context: for architecture analysis — describe the incident (e.g., 'auth-service OOMKilled')

    Returns: JSON matching the respective analysis schema.
    """
    content = await file.read()

    # Resize before encoding — control token cost
    content = _resize_if_needed(content, max_width=1568)

    image_b64 = base64.standard_b64encode(content).decode("utf-8")
    media_type = file.content_type or "image/png"

    if image_type == "architecture":
        result = analyze_architecture_diagram(image_b64, context, media_type)
    else:
        result = analyze_grafana_screenshot(image_b64, media_type)

    return result


def _resize_if_needed(image_bytes: bytes, max_width: int = 1568) -> bytes:
    """Resize image to cap token cost. 1568px wide ≈ 1600 tokens."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        if img.width <= max_width:
            return image_bytes
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return image_bytes  # PIL not installed — send as-is
```

---

## ▶ STOP — do this now

Test the full endpoint with curl:

```bash
# Start AOIS
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &

# Test with a real screenshot
curl -X POST http://localhost:8000/analyze/image \
  -F "file=@grafana_screenshot.png" \
  -F "image_type=grafana" | jq .

# Measure latency — vision calls are 3-8x slower than text-only
time curl -s -X POST http://localhost:8000/analyze/image \
  -F "file=@grafana_screenshot.png" \
  -F "image_type=grafana" > /dev/null
```

Expected latency: **3–8 seconds** for Sonnet with a 1568px screenshot. Text-only `/analyze` calls run in 350–800ms. Vision is 5–15× slower — this is the cost of processing visual tokens.

Expected cost per call: **$0.005–$0.02** depending on image size. Text-only `/analyze` costs ~$0.0002. Vision is 25–100× more expensive per call. This is why vision is reserved for dashboard screenshots, not used on every log event.

The decision rule: use vision when the information needed to diagnose the incident is visible in a dashboard or diagram but not extractable from any single log line. For most incidents, text analysis is sufficient and 100× cheaper.

---

## Latency and Cost Benchmark

Run this benchmark to record your specific numbers:

```python
import time, base64, json, re, os, anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Load a real screenshot
with open("grafana_screenshot.png", "rb") as f:
    img_b64 = base64.standard_b64encode(f.read()).decode()

prompt = """Analyze this Grafana dashboard. Return JSON: {"severity": "P1-P4", "hypothesis": "..."}"""

# Benchmark 3 vision calls
vision_latencies = []
for i in range(3):
    t0 = time.perf_counter()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role":"user","content":[
            {"type":"image","source":{"type":"base64","media_type":"image/png","data":img_b64}},
            {"type":"text","text":prompt},
        ]}],
    )
    latency = (time.perf_counter() - t0) * 1000
    vision_latencies.append(latency)
    tokens = resp.usage.input_tokens
    cost = (tokens / 1_000_000) * 3.0  # Sonnet input pricing approx
    print(f"Vision call {i+1}: {latency:.0f}ms, {tokens} tokens, ~${cost:.4f}")

# Benchmark 3 text-only calls (same incident as text)
text_latencies = []
text_prompt = "auth-service OOMKilled exit code 137. Classify severity and explain. Return JSON."
for i in range(3):
    t0 = time.perf_counter()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role":"user","content":text_prompt}],
    )
    latency = (time.perf_counter() - t0) * 1000
    text_latencies.append(latency)

print(f"\nVision avg: {sum(vision_latencies)/3:.0f}ms")
print(f"Text avg:   {sum(text_latencies)/3:.0f}ms")
print(f"Vision overhead: {sum(vision_latencies)/sum(text_latencies):.1f}x slower")
```

Record your numbers — you will compare them to text-only analysis in the Mastery Checkpoint.

---

## Handling JSON Parse Failures from Vision

Claude Vision produces slightly less consistent JSON than text-only calls, particularly when the image contains no recognizable dashboard structure. Add retry logic:

```python
def analyze_grafana_screenshot(image_b64: str, media_type: str = "image/png") -> dict:
    for attempt in range(2):
        text = _call_vision(image_b64, media_type, _GRAFANA_PROMPT)
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except json.JSONDecodeError:
            pass
        # Second attempt: stricter instruction
        if attempt == 0:
            log.warning("Vision JSON parse failed on attempt 1 — retrying with stricter prompt")

    return {
        "raw_analysis": text,
        "severity": "P3",
        "hypothesis": "Manual review required — vision output was not valid JSON",
        "anomalies": [],
    }
```

The fallback returns a P3 with the raw text so the operator still has Claude's analysis, even if it couldn't be parsed into structured form.

---

## Common Mistakes

### 1. Using Haiku for vision calls

```python
# Wrong — Haiku does not support vision, returns 400
model="claude-haiku-4-5-20251001"

# Correct — Sonnet or Opus for any call that includes an image block
model="claude-sonnet-4-6"
```

This is the most common mistake. If you have automatic model routing, ensure vision calls are pinned to Sonnet before they hit LiteLLM — do not let the router assign Haiku to a request with image content.

### 2. Using `base64.encodebytes()` instead of `base64.standard_b64encode()`

```python
# Wrong — encodebytes() inserts newlines every 76 characters
image_data = base64.encodebytes(f.read()).decode("utf-8")

# Correct — standard_b64encode() produces a single uninterrupted string
image_data = base64.standard_b64encode(f.read()).decode("utf-8")
```

The Anthropic API rejects base64 strings containing newlines with `BadRequestError: Could not process image`. The error message is not obvious — always use `standard_b64encode`.

### 3. Sending full-resolution screenshots without resizing

A 2560×1440 screenshot from a retina display is 3,686 tokens before any text. That's $0.011 in input tokens alone for a single call. At 100 dashboard analyses per day, that's $1.10/day just in image tokens. Resize to 1568px wide before encoding: token count drops to ~1,600 and visual fidelity is sufficient for anomaly detection.

### 4. Vision on empty or minimal dashboards

If you send a screenshot of an empty Grafana dashboard (no data, "No data" placeholders), Claude will describe that accurately: *"This dashboard shows multiple panels with no data loaded."* This is not a hallucination — it is what the image contains. Ensure the dashboard has data before sending it for analysis.

---

## Troubleshooting

### `anthropic.BadRequestError: Could not process image`

Three causes, in order of frequency:
1. Used `base64.encodebytes()` — produces newlines the API rejects. Fix: use `base64.standard_b64encode()`
2. File is not a valid image — empty file, truncated download, wrong extension. Verify: `file grafana_screenshot.png` should show `PNG image data`
3. Image exceeds 5MB — unlikely for screenshots but possible for full-resolution exports. Fix: resize first

### `"I cannot analyze this image" in vision response`

The image is too small (under 100px), too blurry, or visually empty. A 1x1 pixel test PNG will produce this response. Use a real screenshot with visible chart data.

### Vision response has no JSON despite instructing JSON output

The model sometimes adds a preamble before the JSON when the image is ambiguous. The `re.search(r'\{.*\}', text, re.DOTALL)` pattern handles this — it skips any prefix and finds the first valid JSON object. If this still fails, the response contained no JSON-like structure at all — add the retry pattern above.

### Slow vision calls (>10 seconds)

Expected at peak API load. Vision calls are computationally heavier. Mitigation:
- Resize images before sending (reduces token count and processing time)
- Use async calls if analyzing multiple dashboards concurrently
- Cache results for the same image hash if the dashboard is re-analyzed within 5 minutes

---

## Vision Decision Checklist

Before every vision call, ask these three questions. If any answer is "no", use text analysis instead.

At 100 vision calls per day: ~$1.50/day, ~$45/month.
At 1,000 calls per day: ~$15/day, ~$450/month — now the resize discipline matters significantly.
At 100 text-only calls per day: ~$0.02/day — vision is 75× more expensive at the same volume.
The break-even: vision is justified when it replaces 15+ minutes of manual dashboard investigation per incident.
Rule of thumb: if a senior SRE would spend more than 10 minutes looking at a dashboard to diagnose this incident,
the vision call is cheaper than their time even at the highest-volume pricing tier.


1. **Is the information in the image?** — Does the diagnostic value live in the visual structure (chart shape, correlation between panels, topology diagram) rather than in any extractable text or API endpoint?
2. **Is the cost justified?** — At $0.005–$0.02 per call, vision is 25–100× more expensive than text. For a 3am P1, yes. For routine P4 log review, no.
3. **Is the image meaningful?** — A screenshot of an empty dashboard or a tiny 1×1 test image will produce "I cannot analyze this" or a generic description. Verify the image contains actual chart data before sending.

If all three answers are "yes": use vision. Otherwise: use the text `/analyze` endpoint.

---

## Explaining Vision to Three Audiences

**Non-technical (product manager)**: "AOIS used to only read text logs. Now it can read a screenshot of the monitoring dashboard the same way your on-call engineer reads it — and tell you what the spike means before the engineer has even opened their laptop."

**Junior engineer**: "The Anthropic API accepts image content blocks alongside text blocks. Any model call that includes an image must use Sonnet or Opus — Haiku returns a 400. The image is base64-encoded using `standard_b64encode` (not `encodebytes` which adds newlines and breaks the API). The output is the same structured JSON as text analysis — `severity`, `hypothesis`, `anomalies`, `recommended_investigation` — so the dashboard and downstream consumers don't need to change."

**Senior engineer**: "Vision inputs are charged at `(width × height) / 750` input tokens. A 1568×1080 PNG ≈ 2,259 tokens before any text — at Sonnet pricing (~$3/1M input tokens) that is $0.007 in image tokens alone. Resize to 1568px wide before encoding to cap this. JSON compliance with vision responses is slightly lower than text-only (Claude still hits 99%+ but the JSON extractor `re.search(r'\{.*\}', text, re.DOTALL)` is mandatory). The quality argument for vision over text: a Grafana screenshot encodes the cross-correlation between multiple metrics over time — information that exists nowhere in any single log event. For incidents where root cause is visible in a latency graph but not in logs (memory leak causing gradual p99 rise, Redis eviction rate climbing over hours), vision is the only automated path to that evidence."

---

## Connection to Later Phases

### To v34 (Computer Use): vision identifies the anomaly from a screenshot. Computer Use navigates Grafana UI to drill down without a screenshot — full autonomous UI interaction. The two capabilities are complementary: vision for batch analysis (operator uploads a screenshot), computer use for interactive investigation (AOIS navigates Grafana autonomously).

### To v34.5 (Capstone): during the game day, the operator uploads a dashboard screenshot and AOIS provides a vision-enhanced hypothesis alongside the text-log analysis. The combined output — text evidence plus visual pattern recognition — is the most complete automated incident analysis the system produces. Vision latency and cost are part of the capstone cost model.

---

## Mastery Checkpoint

1. Run `analyze_image_from_path` on any screenshot or dashboard image. Show the raw Claude Vision response, unedited.
2. Call the `/analyze/image` endpoint with a Grafana screenshot using curl. Show the complete JSON response including `severity`, `hypothesis`, and at least one `anomaly` entry.
3. Benchmark vision vs text-only calls. Record: vision latency (ms), text latency (ms), vision token count, text token count. Calculate the cost ratio.
4. Send a full-resolution screenshot (if available). Then resize it to 1568px and send again. Compare the token counts and cost. What is the percentage reduction?
5. Explain why `claude-sonnet-4-6` is required for vision calls and `claude-haiku-4-5-20251001` cannot be used. What is the quality tradeoff and the cost difference between the two models for text-only calls?
6. An operator uploads a k8s architecture diagram when auth-service is OOMKilling at 3am. Write the exact `failure_context` string you would pass to `analyze_architecture_diagram`. What specific questions should that context answer?
7. Your team proposes running vision analysis on every log event (not just screenshots). Make the case for and against. What is the cost at 10,000 events/day? When is vision justified vs text-only?

**The mastery bar:** you can submit any Grafana dashboard screenshot to AOIS and receive a structured analysis including severity classification, anomaly timeline, and root cause hypothesis — built from visual content that text logs do not contain. You can explain when this capability justifies its cost and when text-only analysis is sufficient.

---

## 4-Layer Tool Understanding

### Claude Vision (Multimodal API)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | An on-call engineer sees a latency spike on a Grafana dashboard that is not in any single log file — it exists in the shape of the graph over time. Claude Vision reads the image and describes what it sees: "p99 latency began climbing at 03:38, four minutes before the OOMKill alert. The Redis eviction counter jumped simultaneously." Text logs cannot reconstruct that four-minute pre-incident pattern. Vision can. |
| **System Role** | Where does it sit in AOIS? | An additional input channel alongside text logs. Text logs arrive at `/analyze`. Screenshots arrive at `/analyze/image`. Both endpoints produce the same structured output schema (severity, hypothesis, recommended action) — the analysis layer treats them uniformly. Vision analysis is reserved for dashboard screenshots and architecture diagrams — not used on every log event. |
| **Technical** | What is it precisely? | The Anthropic API's multimodal capability: `image` content blocks alongside `text` content blocks in the `messages` array. Images are base64-encoded using `standard_b64encode`. Visual tokens are charged at a higher rate than text tokens. Token count scales with image dimensions: `tokens ≈ (width × height) / 750`. Only Sonnet and Opus models support image blocks — Haiku returns a 400 error. |
| **Remove it** | What breaks, and how fast? | Remove vision → AOIS is text-only. Dashboard screenshots cannot be analyzed. Architecture diagrams cannot be interpreted. The pre-incident signal visible in a latency chart (the gradual climb before the alert) is invisible to AOIS. An operator who screenshots a Grafana anomaly at 3am and pastes it into AOIS gets "I cannot analyze images." Their fastest diagnostic shortcut is severed. |

### PIL / Pillow (Image Processing)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | A full-resolution Grafana screenshot from a 4K monitor is 3MB and 3,686 vision tokens, costing $0.011 per call. PIL resizes it to 1568px wide — 1,600 tokens, $0.005 — without losing the anomaly signal. At 100 analyses/day, that is $220/month vs $400/month. PIL is the cost-control layer for vision inputs. |
| **System Role** | Where does it sit in AOIS? | A pre-processing step in the `/analyze/image` endpoint, before the image is base64-encoded and sent to Claude. Transparent to the caller — they upload a PNG, AOIS resizes it internally if needed. If PIL is not installed, the image is sent as-is (with a log warning). |
| **Technical** | What is it precisely? | Python Imaging Library fork. `Image.open(io.BytesIO(bytes))` parses the image. `img.resize((w, h), Image.LANCZOS)` resizes with high-quality downsampling. `buf = io.BytesIO(); img.save(buf, format="PNG")` re-encodes to bytes. The LANCZOS algorithm preserves sharpness on downscale better than bilinear — important for text legibility in chart labels. |
| **Remove it** | What breaks, and how fast? | Remove PIL → images are sent at original size. A 4K screenshot costs 2× as many tokens. No functional degradation — Claude Vision still works. The cost impact accumulates: at 100 daily analyses, the monthly bill grows by $180. More critically, very large images (>5MB) will be rejected by the API with no fallback. |
