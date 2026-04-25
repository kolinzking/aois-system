# v13.5 — NVIDIA Triton Inference Server: Production Inference Under NIM

⏱ **Estimated time: 6–9 hours**

## What this version builds

In v13 you used NVIDIA NIM and read this in the 4-layer entry: *"NIM is TensorRT-LLM under the hood — the same engine Triton uses, but pre-tuned per model."* That sentence was a forward reference. This version is where it lands.

You will:
1. Deploy Triton locally using its Python backend — no GPU required for the mechanics
2. Build a model repository that serves TinyLlama (the model fine-tuned in v15) on Triton's Python backend
3. Configure dynamic batching and understand the throughput benefit with real numbers
4. Build a model ensemble pipeline (tokenizer → model → formatter as connected stages)
5. Run Perf Analyzer to measure throughput and latency under concurrent load
6. Build the NIM vs Triton vs vLLM decision table from first principles

After this version you can serve any model on Triton, configure it for production throughput, and explain exactly what NIM is doing under the hood.

---

## Prerequisites

v13 complete — NIM routing working in AOIS:
```bash
python -c "
from main import ROUTING_TIERS
names = [t['name'] for t in ROUTING_TIERS]
print(names)
assert 'nim' in names, 'nim tier missing'
print('v13 ok')
"
# Expected:
# ['claude', 'groq', 'nim', 'local']
# v13 ok
```

v15 complete — TinyLlama LoRA adapter in Modal volume:
```bash
python - <<'EOF'
import modal
vol = modal.Volume.lookup("aois-lora-weights")
files = [f.path for f in vol.listdir("/models/tinyllama-sre-lora")]
print(f"Adapter files: {files}")
assert any("adapter_model" in f for f in files), "adapter not found"
print("v15 ok")
EOF
# Expected:
# Adapter files: ['adapter_config.json', 'adapter_model.safetensors', ...]
# v15 ok
```

Docker installed and running:
```bash
docker info --format '{{.ServerVersion}}'
# Expected: 26.x.x or higher
```

Triton client library installed:
```bash
pip install tritonclient[all] geventhttpclient
python -c "import tritonclient.http; print('tritonclient ok')"
# Expected: tritonclient ok
```

**Where each step runs:**

- **Steps 1–5** (Triton mechanics, Python backend, dynamic batching, ensemble, Perf Analyzer):
  CPU only. Run on your local machine or Hetzner server — just Docker, no GPU needed.
- **Step 6** (TinyLlama on GPU): Runs on **Vast.ai**. Rent an RTX 3090 ($0.13/hr) or RTX 4090
  ($0.29/hr) — same SSH model as v14. Total GPU time for this step: ~30–45 min = ~$0.10.

If you want to complete Steps 1–5 first and defer Step 6, that is fine. The mechanics are
identical on GPU; only the `instance_group kind` in `config.pbtxt` changes from `KIND_CPU`
to `KIND_GPU`, and the Docker run command adds `--gpus all`.

---

## Learning Goals

By the end you will be able to:
- Explain what Triton is, why it exists, and how it relates to NIM and vLLM
- Build a model repository with a correct `config.pbtxt` for a Python backend model
- Serve a PEFT LoRA model on Triton using the Python backend
- Configure dynamic batching and justify a `max_queue_delay_microseconds` value
- Build a two-stage model ensemble and explain when ensemble vs monolithic matters
- Run Perf Analyzer, interpret throughput (infer/sec) and p95 latency, and identify the saturation point
- Choose between NIM, Triton, and vLLM for a given production scenario with a written rationale

---

## The Problem NIM Hides From You

In v13 you added NIM to AOIS with this:

```python
{
    "name": "nim",
    "model": "nim/meta/llama-3.1-8b-instruct",
    "api_base": "https://integrate.api.nvidia.com/v1",
    "condition": lambda severity, _: severity in ["P3", "P4"],
}
```

One line. The NGC API responds. You never had to think about the inference server underneath.

Now ask: **what is `https://integrate.api.nvidia.com/v1` actually running?**

The answer is Triton. Specifically: Triton Inference Server with the TensorRT-LLM backend, serving
a model that NVIDIA pre-compiled for the specific GPU hardware in their NGC cluster. The
OpenAI-compatible HTTP interface is a thin wrapper around Triton's HTTP port 8000.

When you deploy your own NIM container — the Modal path in v13's Step 4 — you run a container
that spins up Triton internally. `docker run nvcr.io/nim/meta/llama-3.1-8b-instruct` starts
Triton, loads the TensorRT-compiled model, and exposes port 8000. NIM's value is the packaging:
the model is pre-compiled, pre-quantized, and pre-tuned for NVIDIA hardware so you do not have
to do it yourself.

Triton without NIM: you control everything — any model, any backend, any batching configuration
— but you configure all of it yourself. This version builds that understanding from scratch.

---

## What Triton Is

**NVIDIA Triton Inference Server** is an open-source inference serving platform. It accepts models
from multiple frameworks (TensorRT, ONNX, PyTorch, Python), hosts them simultaneously, and serves
them via HTTP (port 8000), gRPC (port 8001), and Prometheus metrics (port 8002).

The mental model: Triton is to AI models what nginx is to web applications. nginx does not care
what language your app is written in — it routes HTTP to whatever is behind it. Triton does not
care what framework your model uses — it routes inference requests to whatever backend handles
that model type.

**Three components you interact with:**

**1. Model Repository** — a filesystem directory Triton reads on startup. Every model is a
subdirectory with a `config.pbtxt` and a versioned directory (`1/`) containing the model
artifact. Change a file in the repository and Triton hot-reloads that model within 5 seconds
without restarting.

**2. Backend** — the runtime that executes inference for a specific model type. Python backend,
TensorRT-LLM backend, ONNX Runtime backend, PyTorch backend. Each is a plugin loaded dynamically.
NIM ships with TensorRT-LLM backend pre-configured. You install Python backend separately.

**3. Inference Protocol** — the HTTP/gRPC API surface. The same endpoint serves every model in
the repository. `/v2/models/{model_name}/infer` for HTTP. `/v2/models/{model_name}` for metadata.

---

## The Model Repository: The Only Thing Triton Requires

Triton does not have a configuration file for the server itself. It has a model repository.
Put a directory here with the right structure and Triton serves it. Change the directory and
Triton hot-reloads without restart.

Minimal structure:
```
model_repository/
  my_model/
    config.pbtxt        ← required: model metadata, backend, inputs/outputs
    1/                  ← required: version directory (1, 2, 3 — integers only)
      model.py          ← Python backend: model.py
      model.onnx        ← ONNX backend: model.onnx
      model.plan        ← TensorRT backend: model.plan
```

The version directory name is just an integer. Triton serves the highest version by default.
Rolling back is `mv 3/ 3-bad/` — Triton detects the change and rolls back to version 2 within
5 seconds. This is your rollback mechanism.

### config.pbtxt

Every model needs a `config.pbtxt`. It is Protocol Buffers text format — not YAML, not JSON.
It defines:

- `name`: must exactly match the directory name
- `backend`: which backend handles this model (`"python"`, `"onnxruntime"`, `"tensorrt"`, `"vllm"`)
- `input`: tensor names, data types, and shapes the model accepts
- `output`: tensor names, data types, and shapes the model returns
- `instance_group`: how many copies of the model to load, and on which device
- `dynamic_batching`: optional; tells Triton to batch concurrent requests before executing

Minimal config for a Python backend model:
```protobuf
name: "my_model"
backend: "python"

input [
  {
    name: "INPUT_TEXT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

output [
  {
    name: "OUTPUT_TEXT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

instance_group [
  {
    kind: KIND_CPU
    count: 1
  }
]
```

`instance_group` tells Triton how many copies of the model to load. `KIND_CPU` runs on CPU.
`KIND_GPU` runs on GPU (add a `gpus: [0]` field for GPU index). `count: 2` means two parallel
instances — Triton load-balances requests across them.

---

## Step 1: Run Triton Locally (CPU, No Model)

Start a Triton container with an empty model repository. This verifies your setup before adding
any models.

```bash
mkdir -p /tmp/triton_models

docker run --rm -d \
  --name triton-aois \
  -p 8000:8000 \
  -p 8001:8001 \
  -p 8002:8002 \
  -v /tmp/triton_models:/models \
  nvcr.io/nvidia/tritonserver:24.01-py3 \
  tritonserver --model-repository=/models --log-verbose=1
```

The image is ~8GB on first pull. If it is not cached:
```bash
docker pull nvcr.io/nvidia/tritonserver:24.01-py3
# Expected: pulls multiple layers, ends with:
# Status: Downloaded newer image for nvcr.io/nvidia/tritonserver:24.01-py3
```

Wait 15 seconds for startup, then verify:
```bash
curl -s localhost:8000/v2/health/ready && echo "OK"
# Expected: OK

curl -s localhost:8000/v2 | python3 -m json.tool
# Expected:
# {
#     "name": "triton",
#     "version": "2.43.0",
#     "extensions": [
#         "classification",
#         "sequence",
#         "model_repository",
#         "model_repository(unload_dependents)",
#         ...
#     ]
# }
```

Check Prometheus metrics:
```bash
curl -s localhost:8002/metrics | grep "^# HELP nv_inference" | head -5
# Expected:
# # HELP nv_inference_request_success Total number of successful inference requests, including cache hits
# # HELP nv_inference_request_failure Total number of failed inference requests
# # HELP nv_inference_count Total number of inferences performed (does not include cache hits)
# # HELP nv_inference_exec_count Total number of model executions performed
# # HELP nv_inference_request_duration_us Cumulative inference request duration in microseconds
```

These metrics feed directly into AOIS's Prometheus stack. In v16 you added `otel/prometheus.yml`
with scrape configs — adding Triton is one additional `scrape_config` block pointing at `:8002`.

Triton is running with zero models. All `/v2/models/*` calls return 404 until you add models.

---

## Step 2: Python Backend — Your First Model

The Python backend runs any Python code as a Triton model. You define a class with three methods
and Triton calls them. This is how you serve a PEFT model, a preprocessing step, a custom
postprocessor, or any logic that does not fit a standard ML framework.

### The model.py contract

```python
import numpy as np
import triton_python_backend_utils as pb_utils


class TritonPythonModel:

    def initialize(self, args):
        # Called once when Triton loads the model.
        # Load weights, set up tokenizer, warm up GPU here.
        # args["model_repository"] — path to this model's directory
        # args["model_config"]    — JSON string of config.pbtxt content
        pass

    def execute(self, requests):
        # Called for each batch of inference requests.
        # requests: list of pb_utils.InferenceRequest (1 to preferred_batch_size items)
        # Must return: list of pb_utils.InferenceResponse — same length as requests.
        responses = []
        for request in requests:
            inp = pb_utils.get_input_tensor_by_name(request, "INPUT_TEXT")
            text = inp.as_numpy()[0].decode("utf-8")

            result = text.upper()  # your inference logic here

            out_tensor = pb_utils.Tensor(
                "OUTPUT_TEXT",
                np.array([result.encode("utf-8")], dtype=object),
            )
            responses.append(pb_utils.InferenceResponse(output_tensors=[out_tensor]))
        return responses

    def finalize(self):
        # Called once when Triton unloads the model.
        # Release GPU memory, close connections here.
        pass
```

The key constraint: `execute()` receives a list and must return a list of the same length.
Whether dynamic batching delivers 1 request or 16, the loop handles them all.

### Build an echo model

```bash
mkdir -p /tmp/triton_models/aois_echo/1

cat > /tmp/triton_models/aois_echo/config.pbtxt << 'EOF'
name: "aois_echo"
backend: "python"

input [
  {
    name: "INPUT_TEXT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

output [
  {
    name: "OUTPUT_TEXT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

instance_group [
  {
    kind: KIND_CPU
    count: 2
  }
]
EOF

cat > /tmp/triton_models/aois_echo/1/model.py << 'EOF'
import numpy as np
import triton_python_backend_utils as pb_utils


class TritonPythonModel:
    def initialize(self, args):
        print("[aois_echo] initialized")

    def execute(self, requests):
        responses = []
        for request in requests:
            inp = pb_utils.get_input_tensor_by_name(request, "INPUT_TEXT")
            text = inp.as_numpy()[0].decode("utf-8")
            result = f"echo: {text}"
            out = pb_utils.Tensor(
                "OUTPUT_TEXT",
                np.array([result.encode("utf-8")], dtype=object),
            )
            responses.append(pb_utils.InferenceResponse(output_tensors=[out]))
        return responses

    def finalize(self):
        print("[aois_echo] finalized")
EOF
```

Triton polls the model repository every 5 seconds. Wait, then verify it loaded:
```bash
sleep 8
curl -s localhost:8000/v2/models/aois_echo/ready && echo "READY"
# Expected: READY

curl -s localhost:8000/v2/models/aois_echo | python3 -m json.tool
# Expected:
# {
#     "name": "aois_echo",
#     "versions": ["1"],
#     "platform": "python",
#     "inputs": [{"name": "INPUT_TEXT", "datatype": "BYTES", ...}],
#     "outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES", ...}]
# }
```

Run an inference request:
```python
# test_echo.py
import tritonclient.http as httpclient
import numpy as np

client = httpclient.InferenceServerClient(url="localhost:8000")

log = "OOMKilled: exit code 137"
data = np.array([[log.encode("utf-8")]], dtype=object)

inputs = [httpclient.InferInput("INPUT_TEXT", data.shape, "BYTES")]
inputs[0].set_data_from_numpy(data)
outputs = [httpclient.InferRequestedOutput("OUTPUT_TEXT")]

resp = client.infer(model_name="aois_echo", inputs=inputs, outputs=outputs)
result = resp.as_numpy("OUTPUT_TEXT")[0][0].decode("utf-8")
print(result)
```

```bash
python3 test_echo.py
# Expected:
# echo: OOMKilled: exit code 137
```

You have a working Triton model. The mechanics are identical for a 1.1B parameter language model
— only `execute()` changes.

### ▶ STOP — do this now

1. Run `test_echo.py` and confirm the output.
2. Add a second version: create `/tmp/triton_models/aois_echo/2/model.py` where `execute()`
   returns `f"v2: {text}"` instead of `f"echo: {text}"`. Wait 8 seconds and verify Triton now
   shows `"versions": ["1", "2"]` and serves the v2 model by default.
3. Check what happens when you call a model that does not exist:
   ```bash
   curl -s localhost:8000/v2/models/does_not_exist/ready
   # Expected: HTTP 400 — model not found
   ```

---

## Step 3: Dynamic Batching — Why Throughput Scales

Single-request inference underutilizes GPU. If 10 requests arrive within 5ms of each other,
processing them one at a time means the GPU executes 10 separate forward passes. Dynamic batching
tells Triton: collect requests for up to X microseconds, then execute them together as one batch.

The result: 10 requests batched together complete in roughly the same time as 2–3 requests
executed sequentially. A GPU forward pass over a batch of 10 is not 10× slower than a batch of
1 — it is 1.5–2× slower. You get 10 results for the cost of 2. This is GPU parallelism.

Update `config.pbtxt` for `aois_echo`:
```protobuf
name: "aois_echo"
backend: "python"

input [
  {
    name: "INPUT_TEXT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

output [
  {
    name: "OUTPUT_TEXT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

dynamic_batching {
  preferred_batch_size: [4, 8, 16]
  max_queue_delay_microseconds: 5000
}

instance_group [
  {
    kind: KIND_CPU
    count: 2
  }
]
```

**`preferred_batch_size: [4, 8, 16]`**: When 4 requests accumulate in the queue, Triton dispatches
immediately without waiting for the full delay. 8 and 16 are also preferred trigger points.
Triton always dispatches at `max_queue_delay_microseconds` even if no preferred size is reached.

**`max_queue_delay_microseconds: 5000`**: 5ms maximum wait. A lone request in the queue for 5ms
gets dispatched regardless. This is your latency cap per request. For AOIS P1 incidents that
need sub-30s analysis, 5ms is imperceptible. For a high-throughput P3/P4 tier, increase to
50ms to allow larger batches to form.

**`instance_group count: 2`**: Two model instances run in parallel. Triton load-balances across
them. On GPU, this could be two instances on the same GPU (sharing VRAM) or across two GPUs.
On CPU, two threads.

The tradeoff: larger `preferred_batch_size` increases throughput but also increases worst-case
latency for a single request (it waits for the batch to fill). Set this based on your SLO:
- P1 incidents (SLO: 30s) — small batches or none
- P3/P4 volume tier (SLO: 60s) — aggressive batching

### ▶ STOP — do this now

Update your `aois_echo/config.pbtxt` with the dynamic batching block above.
Wait 8 seconds for hot-reload, then run 10 concurrent requests and measure throughput:

```python
# test_concurrent.py
import tritonclient.http as httpclient
import numpy as np
import time
import concurrent.futures

client = httpclient.InferenceServerClient(url="localhost:8000")

def single_infer(text):
    data = np.array([[text.encode("utf-8")]], dtype=object)
    inputs = [httpclient.InferInput("INPUT_TEXT", data.shape, "BYTES")]
    inputs[0].set_data_from_numpy(data)
    outputs = [httpclient.InferRequestedOutput("OUTPUT_TEXT")]
    r = client.infer(model_name="aois_echo", inputs=inputs, outputs=outputs)
    return r.as_numpy("OUTPUT_TEXT")[0][0].decode("utf-8")

logs = [f"pod-{i} OOMKilled exit code 137" for i in range(10)]

start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(single_infer, logs))
elapsed = time.time() - start

print(f"10 concurrent requests: {elapsed:.3f}s")
print(f"Throughput: {10 / elapsed:.1f} req/s")
print(f"Sample: {results[0]}")
```

```bash
python3 test_concurrent.py
# Expected (CPU echo model, dynamic batching active):
# 10 concurrent requests: 0.04–0.15s
# Throughput: 67–250 req/s
# Sample: v2: pod-0 OOMKilled exit code 137
```

These numbers are CPU overhead, not inference time. On GPU with a real model, the batching
benefit is pronounced — a batch of 8 TinyLlama inferences is ~3× faster than 8 sequential
inferences.

---

## Step 4: Model Ensemble — Chaining Models in Triton

An ensemble is a pipeline of models where Triton routes tensors between them without returning
to the client. Instead of your application calling tokenize → infer → format, the ensemble
does it all internally. The client sends raw text and receives structured JSON.

```
Client → "OOMKilled exit code 137"
         ↓ [Triton routes tensor internally]
         [aois_tokenizer]  → token_ids tensor
         ↓
         [aois_llm]        → output_ids tensor
         ↓
         [aois_formatter]  → {"severity":"P2","summary":"..."}
         ↑
Client ← structured JSON (one HTTP call)
```

Three models, one HTTP call. Triton handles the intermediate tensor routing.

### Ensemble config.pbtxt

```protobuf
name: "aois_pipeline"
platform: "ensemble"

input [
  {
    name: "PIPELINE_INPUT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

output [
  {
    name: "PIPELINE_OUTPUT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

ensemble_scheduling {
  step [
    {
      model_name: "aois_tokenizer"
      model_version: -1
      input_map {
        key: "RAW_TEXT"
        value: "PIPELINE_INPUT"
      }
      output_map {
        key: "TOKEN_IDS"
        value: "tokenizer_output"
      }
    },
    {
      model_name: "aois_llm"
      model_version: -1
      input_map {
        key: "INPUT_IDS"
        value: "tokenizer_output"
      }
      output_map {
        key: "OUTPUT_IDS"
        value: "llm_output"
      }
    },
    {
      model_name: "aois_formatter"
      model_version: -1
      input_map {
        key: "RAW_OUTPUT"
        value: "llm_output"
      }
      output_map {
        key: "FORMATTED_OUTPUT"
        value: "PIPELINE_OUTPUT"
      }
    }
  ]
}
```

Key points:
- `platform: "ensemble"` — no backend field; Triton handles tensor routing itself
- `model_version: -1` — always use the latest deployed version of each component model
- `input_map` / `output_map` — `key` is the component model's tensor name, `value` is the
  pipeline-internal tensor name passed between steps
- Each step model (`aois_tokenizer`, `aois_llm`, `aois_formatter`) must exist separately in
  the model repository with matching tensor names

### Build a two-model ensemble demo

Wire `aois_echo` into a model that uppercases its output:

```bash
# First: create the uppercase model
mkdir -p /tmp/triton_models/aois_upper/1

cat > /tmp/triton_models/aois_upper/config.pbtxt << 'EOF'
name: "aois_upper"
backend: "python"
input [{ name: "LOWER_TEXT" data_type: TYPE_BYTES dims: [1] }]
output [{ name: "UPPER_TEXT" data_type: TYPE_BYTES dims: [1] }]
instance_group [{ kind: KIND_CPU count: 1 }]
EOF

cat > /tmp/triton_models/aois_upper/1/model.py << 'EOF'
import numpy as np
import triton_python_backend_utils as pb_utils

class TritonPythonModel:
    def initialize(self, args): pass
    def execute(self, requests):
        responses = []
        for req in requests:
            inp = pb_utils.get_input_tensor_by_name(req, "LOWER_TEXT")
            text = inp.as_numpy()[0].decode("utf-8").upper()
            out = pb_utils.Tensor("UPPER_TEXT", np.array([text.encode("utf-8")], dtype=object))
            responses.append(pb_utils.InferenceResponse(output_tensors=[out]))
        return responses
    def finalize(self): pass
EOF

# Now: create the ensemble
mkdir -p /tmp/triton_models/aois_echo_upper

cat > /tmp/triton_models/aois_echo_upper/config.pbtxt << 'EOF'
name: "aois_echo_upper"
platform: "ensemble"

input [{ name: "RAW_INPUT" data_type: TYPE_BYTES dims: [1] }]
output [{ name: "FINAL_OUTPUT" data_type: TYPE_BYTES dims: [1] }]

ensemble_scheduling {
  step [
    {
      model_name: "aois_echo"
      model_version: -1
      input_map  { key: "INPUT_TEXT" value: "RAW_INPUT" }
      output_map { key: "OUTPUT_TEXT" value: "echo_result" }
    },
    {
      model_name: "aois_upper"
      model_version: -1
      input_map  { key: "LOWER_TEXT" value: "echo_result" }
      output_map { key: "UPPER_TEXT" value: "FINAL_OUTPUT" }
    }
  ]
}
EOF
```

Wait 8 seconds for hot-reload, then test:
```python
# test_ensemble.py
import tritonclient.http as httpclient
import numpy as np

client = httpclient.InferenceServerClient(url="localhost:8000")

text = "pod crashed with OOMKilled"
data = np.array([[text.encode("utf-8")]], dtype=object)
inputs = [httpclient.InferInput("RAW_INPUT", data.shape, "BYTES")]
inputs[0].set_data_from_numpy(data)
outputs = [httpclient.InferRequestedOutput("FINAL_OUTPUT")]

resp = client.infer(model_name="aois_echo_upper", inputs=inputs, outputs=outputs)
print(resp.as_numpy("FINAL_OUTPUT")[0][0].decode("utf-8"))
```

```bash
python3 test_ensemble.py
# Expected:
# ECHO: POD CRASHED WITH OOMKILLED
```

One HTTP call. Two models ran. Client saw none of it.

**When ensemble is worth it:**
- Separate teams own preprocessing vs model vs postprocessing — each stage deploys independently
- You want to A/B test one stage without redeploying the others
- You want Triton to handle backpressure and queuing between stages automatically

**When ensemble is not worth it:**
- You own the whole pipeline and it is simple — just chain calls in your application code
- You need cross-stage shared state that is not a tensor (ensemble passes tensors only)

---

## Step 5: Perf Analyzer — Measure Before You Claim Performance

Perf Analyzer is NVIDIA's load testing tool for Triton. It generates concurrent inference
requests, sweeps concurrency levels, and reports throughput and tail latency at each level.
Run this before any performance claim in production.

The SDK container ships Perf Analyzer:
```bash
docker run --rm --net=host \
  nvcr.io/nvidia/tritonserver:24.01-py3-sdk \
  perf_analyzer \
    -m aois_echo \
    -u localhost:8000 \
    --protocol http \
    --input-data zero \
    --shape INPUT_TEXT:1 \
    --concurrency-range 1:16:2 \
    --measurement-interval 5000 \
    --percentile 95
```

Flag breakdown:
- `--input-data zero`: send zero-filled byte inputs — measuring server overhead, not model work
- `--shape INPUT_TEXT:1`: our input tensor has shape [1]
- `--concurrency-range 1:16:2`: test at 1, 3, 5, 7, 9, 11, 13, 15 concurrent clients
- `--measurement-interval 5000`: measure for 5 seconds at each concurrency level
- `--percentile 95`: report p95 latency — production cares about tail latency, not mean

Expected output (partial, CPU echo model):
```
Concurrency: 1,  throughput: 1247.3 infer/sec,  latency p95:  801 usec
Concurrency: 3,  throughput: 3098.1 infer/sec,  latency p95:  972 usec
Concurrency: 5,  throughput: 4872.6 infer/sec,  latency p95: 1031 usec
Concurrency: 7,  throughput: 5621.4 infer/sec,  latency p95: 1248 usec
Concurrency: 9,  throughput: 5884.2 infer/sec,  latency p95: 1540 usec
Concurrency: 11, throughput: 5901.7 infer/sec,  latency p95: 1934 usec
Concurrency: 13, throughput: 5894.3 infer/sec,  latency p95: 2421 usec
Concurrency: 15, throughput: 5888.9 infer/sec,  latency p95: 2647 usec
```

Reading the results:

**Throughput plateaus at concurrency 9–11.** Adding more concurrent clients after this point
does not improve throughput — you have saturated all model instances. This is the saturation
point. It is determined by `instance_group count` (2 instances × CPU threads available).

**Latency rises with concurrency.** At concurrency 15, p95 latency is 3× the concurrency-1
latency. Queue depth is increasing. Requests wait longer for an available instance.

**The knee of the curve** (concurrency 7 here): near-maximum throughput before latency degrades.
This is the sweet spot. Setting `preferred_batch_size` to a value near this concurrency level
allows Triton to form full batches efficiently.

To raise the saturation point: increase `instance_group count` from 2 to 4. Two more parallel
model instances double the throughput ceiling. On GPU, increasing count also increases VRAM usage
— there is a hard ceiling at GPU memory capacity.

### ▶ STOP — do this now

Run Perf Analyzer against `aois_echo` with `--concurrency-range 1:8:1`. Record throughput and
p95 latency at each level. Answer three questions before continuing:

1. At what concurrency does throughput plateau?
2. At what concurrency does p95 latency cross 1.5ms?
3. If your SLO for P3/P4 analysis is 500ms p95, and TinyLlama on GPU takes 350ms for a single
   request, what is the maximum concurrency you can sustain before Triton queue overhead pushes
   you over SLO?

Expected answer to (3): at the echo model's scaling ratio, ~3–4ms of Triton overhead at
concurrency 10 means a 350ms model becomes ~354ms — well within 500ms SLO. The answer is:
Triton's queuing overhead is negligible relative to model inference time. The SLO constraint
for TinyLlama will be model latency, not Triton overhead.

---

## Step 6: Deploying TinyLlama on Triton (GPU Required — Vast.ai)

Same model as v15, different server. Triton's Python backend vs vLLM — this demonstrates the
difference: Triton is a general-purpose container, vLLM is LLM-optimized. Both serve the same
LoRA-adapted model.

**Before starting Step 6:** rent a Vast.ai RTX 3090 or RTX 4090 and SSH in (same process as
v14 Steps 1–2). Keep the SSH port-forward and instance running throughout Step 6.

### Step 6a: Export the LoRA adapter from Modal and copy to Vast.ai

The adapter is in a Modal volume. Export it locally:

```python
# export_adapter.py
import modal
import os

vol = modal.Volume.lookup("aois-lora-weights")
export_dir = "./triton_adapter"
os.makedirs(export_dir, exist_ok=True)

for entry in vol.listdir("/models/tinyllama-sre-lora"):
    fname = os.path.basename(entry.path)
    local_path = os.path.join(export_dir, fname)
    print(f"Downloading {fname} ...")
    with open(local_path, "wb") as f:
        for chunk in vol.read_file(f"/models/tinyllama-sre-lora/{fname}"):
            f.write(chunk)

print("Export complete")
```

```bash
# Run on your LOCAL machine — this pulls from Modal, not Vast.ai
python3 export_adapter.py
# Expected:
# Downloading adapter_config.json ...
# Downloading adapter_model.safetensors ...
# Downloading tokenizer.json ...
# Downloading tokenizer_config.json ...
# Downloading special_tokens_map.json ...
# Export complete

ls -lh triton_adapter/
# adapter_config.json         ~1KB
# adapter_model.safetensors  ~9MB
# tokenizer.json              ~2MB
# tokenizer_config.json       ~1KB
# special_tokens_map.json     ~1KB
```

Now copy the adapter to your Vast.ai instance:

```bash
# Replace 12345 and 1.2.3.4 with your actual Vast.ai SSH port and IP
scp -P 12345 -r ./triton_adapter/ root@1.2.3.4:/tmp/triton_adapter/
# Expected:
# adapter_config.json       100%  1KB
# adapter_model.safetensors 100%  9MB   4.2MB/s
# tokenizer.json            100%  2MB
# tokenizer_config.json     100%  1KB
# special_tokens_map.json   100%  1KB

# Verify it arrived on Vast.ai
ssh -p 12345 root@1.2.3.4 "ls -lh /tmp/triton_adapter/"
# Expected: same 5 files listed above
```

All remaining steps in Step 6 run **on the Vast.ai instance** (inside your SSH session).

### Step 6b: Build the model repository

```bash
# On Vast.ai — the adapter is now at /tmp/triton_adapter/
mkdir -p /tmp/triton_models/aois_tinyllama/1
cp -r /tmp/triton_adapter /tmp/triton_models/aois_tinyllama/lora_adapter

cat > /tmp/triton_models/aois_tinyllama/config.pbtxt << 'EOF'
name: "aois_tinyllama"
backend: "python"

input [
  {
    name: "LOG_TEXT"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

output [
  {
    name: "ANALYSIS_JSON"
    data_type: TYPE_BYTES
    dims: [1]
  }
]

dynamic_batching {
  preferred_batch_size: [1, 2, 4]
  max_queue_delay_microseconds: 10000
}

instance_group [
  {
    kind: KIND_GPU
    gpus: [0]
    count: 1
  }
]

parameters {
  key: "base_model"
  value { string_value: "TinyLlama/TinyLlama-1.1B-Chat-v1.0" }
}

parameters {
  key: "adapter_path"
  value { string_value: "/models/aois_tinyllama/lora_adapter" }
}
EOF
```

### Step 6c: Write model.py

```python
# /tmp/triton_models/aois_tinyllama/1/model.py
import json
import numpy as np
import triton_python_backend_utils as pb_utils
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel


class TritonPythonModel:
    def initialize(self, args):
        cfg = json.loads(args["model_config"])
        params = {p["key"]: p["value"]["string_value"]
                  for p in cfg.get("parameters", [])}

        base_id = params.get("base_model", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
        adapter = params.get("adapter_path", "/models/aois_tinyllama/lora_adapter")

        print(f"[aois_tinyllama] loading base: {base_id}")
        self.tokenizer = AutoTokenizer.from_pretrained(base_id)
        base = AutoModelForCausalLM.from_pretrained(
            base_id, torch_dtype=torch.float16, device_map="cuda:0"
        )

        print(f"[aois_tinyllama] loading adapter: {adapter}")
        self.model = PeftModel.from_pretrained(base, adapter)
        self.model.eval()

        self.system_prompt = (
            "You are an SRE log analysis assistant. "
            "Return a JSON object with keys: summary, severity (P1-P4), "
            "suggested_action, confidence (0.0-1.0). Return only valid JSON."
        )
        print("[aois_tinyllama] ready")

    def execute(self, requests):
        responses = []
        for request in requests:
            inp = pb_utils.get_input_tensor_by_name(request, "LOG_TEXT")
            log = inp.as_numpy()[0].decode("utf-8")

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Log: {log}"},
            ]
            prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            enc = self.tokenizer(prompt, return_tensors="pt").to("cuda:0")

            with torch.no_grad():
                out_ids = self.model.generate(
                    **enc,
                    max_new_tokens=150,
                    temperature=0.1,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id,
                )

            generated = self.tokenizer.decode(
                out_ids[0][enc["input_ids"].shape[1]:],
                skip_special_tokens=True,
            ).strip()

            if "```json" in generated:
                generated = generated.split("```json")[1].split("```")[0].strip()
            elif "```" in generated:
                generated = generated.split("```")[1].split("```")[0].strip()

            try:
                json.loads(generated)
            except json.JSONDecodeError:
                generated = json.dumps({
                    "summary": generated[:200],
                    "severity": "P3",
                    "suggested_action": "manual review required",
                    "confidence": 0.3,
                })

            out = pb_utils.Tensor(
                "ANALYSIS_JSON",
                np.array([generated.encode("utf-8")], dtype=object),
            )
            responses.append(pb_utils.InferenceResponse(output_tensors=[out]))
        return responses

    def finalize(self):
        del self.model
        torch.cuda.empty_cache()
        print("[aois_tinyllama] finalized")
```

### Step 6d: Launch Triton with GPU access (on Vast.ai)

```bash
# On Vast.ai — first verify Docker sees your GPU
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
# Expected: shows your RTX 3090 or RTX 4090, 24576MiB

# Pull the Triton image (nvcr.io/nvidia/tritonserver is public — no NGC auth needed)
# First pull is ~8GB, subsequent runs use cached image
docker pull nvcr.io/nvidia/tritonserver:24.01-py3
# Expected: Status: Downloaded newer image for nvcr.io/nvidia/tritonserver:24.01-py3

# Start Triton with GPU passthrough
docker run --rm -d \
  --gpus all \
  --name triton-aois-gpu \
  -p 8000:8000 -p 8001:8001 -p 8002:8002 \
  -v /tmp/triton_models:/models \
  nvcr.io/nvidia/tritonserver:24.01-py3 \
  tritonserver \
    --model-repository=/models \
    --backend-config=python,shm-default-byte-size=67108864 \
    --log-verbose=0
```

Watch for model load (takes 30–90s on RTX 3090 — downloads TinyLlama base weights ~2.2GB):
```bash
docker logs -f triton-aois-gpu 2>&1 | grep -E "aois_tinyllama|READY|ERROR"
# Expected:
# ... [aois_tinyllama] loading base: TinyLlama/TinyLlama-1.1B-Chat-v1.0
# ... [aois_tinyllama] loading adapter: /models/aois_tinyllama/lora_adapter
# ... [aois_tinyllama] ready
# ... Successfully loaded model 'aois_tinyllama'
```

For the inference test, forward the Triton port back to your local machine:
```bash
# In a new local terminal — forward Vast.ai port 8000 to local 8000
ssh -N -L 8000:localhost:8000 -p 12345 root@1.2.3.4
# Leave running while you test
```

Test inference (run locally — hits Vast.ai Triton via port forward):
```python
# test_tinyllama_triton.py
import tritonclient.http as httpclient
import numpy as np
import json
import time

client = httpclient.InferenceServerClient(url="localhost:8000")

test_logs = [
    "pod OOMKilled exit code 137, container memory limit 512Mi exceeded",
    "CrashLoopBackOff: container restarting every 30s, exit code 1",
    "disk pressure: node condition DiskPressure=True, available 2%",
]

for log in test_logs:
    data = np.array([[log.encode("utf-8")]], dtype=object)
    inputs = [httpclient.InferInput("LOG_TEXT", data.shape, "BYTES")]
    inputs[0].set_data_from_numpy(data)
    outputs = [httpclient.InferRequestedOutput("ANALYSIS_JSON")]

    t0 = time.time()
    resp = client.infer(model_name="aois_tinyllama", inputs=inputs, outputs=outputs)
    ms = (time.time() - t0) * 1000

    result = json.loads(resp.as_numpy("ANALYSIS_JSON")[0][0].decode("utf-8"))
    print(f"severity={result.get('severity')}  confidence={result.get('confidence')}  latency={ms:.0f}ms")
    print(f"  {result.get('summary', '')[:80]}")
```

```bash
python3 test_tinyllama_triton.py
# Expected (RTX 3090 or RTX 4090):
# severity=P2  confidence=0.85  latency=380-450ms
#   Memory limit exceeded causing OOM kill
# severity=P2  confidence=0.80  latency=360-420ms
#   Container restart loop due to application crash
# severity=P3  confidence=0.75  latency=380-440ms
#   Node disk pressure critical
```

Same model as v15, ~400ms on RTX 3090 via Triton Python backend. SGLang on the same hardware
runs the same model at ~250–350ms for warm requests (RadixAttention kicks in after the first).
The gap is the Triton Python backend's overhead: it does not use PagedAttention or RadixAttention.
SGLang/vLLM is the right choice for pure LLM serving. Triton is the right choice when you need
to serve this model alongside embedders, rerankers, and other model types on the same GPU.

### ▶ STOP — do this now

Run `test_tinyllama_triton.py`. Then run the same three log inputs through Groq (from your
existing AOIS routing code) and record both latency and cost. Fill in this table:

| Tier | Latency (ms) | Cost/call | Infrastructure |
|------|-------------|-----------|----------------|
| Groq API | ? | $0.000001 | Zero |
| Triton + TinyLlama (GPU) | ? | GPU-hours | Self-managed |

The answer tells you the break-even point for running your own GPU instance versus paying Groq
per call. (Spoiler from v13: at ~3,000 P3/P4 calls/day, Groq at $0.000001/call is ~$0.003/day.
A Vast.ai RTX 3090 at $0.13/hr × 24hr = $3.12/day. You would need >3,120 calls/day for self-hosted
GPU to be cheaper than Groq. At that volume it is worth it — but remember the main reason to
self-host is not cost at this scale, it is running your fine-tuned model that Groq cannot serve.)

---

## Step 7: NIM vs Triton vs vLLM — The Decision Framework

You have now used all three. Here is the framework from first principles:

| Dimension | NVIDIA NIM | Triton | vLLM |
|-----------|-----------|--------|------|
| **What it is** | Packaged Triton + TensorRT-LLM for NGC-catalog models | General inference server, any model, any backend | LLM-specific engine with PagedAttention + continuous batching |
| **Model support** | NGC catalog only | Any model, any framework | Any HuggingFace model |
| **LLM performance** | Best for NGC models (pre-compiled TensorRT) | Good — Python backend overhead ~30% vs vLLM | Best for LLMs: PagedAttention halves memory, continuous batching saturates GPU |
| **LoRA adapters** | Not on NGC API; beta on self-hosted NIM | First-class via Python backend (any PEFT model) | First-class (`--enable-lora` flag) |
| **Multi-model hosting** | One model per container | Multiple models in one server | One model per server (default) |
| **Setup complexity** | `docker run nvcr.io/nim/...` — minutes | Model repo + config.pbtxt per model — hours | `vllm serve model_id` — minutes |
| **Prometheus metrics** | Port 8002 (Triton underneath) | Port 8002 | `/metrics` endpoint |
| **When to use** | NGC model, zero config needed | Mixed model types on shared GPU, or custom model + production serving | Any LLM at maximum throughput |

**AOIS decision matrix:**

| Scenario | Choice | Reason |
|----------|--------|--------|
| P3/P4 volume, NGC model, NGC API key exists | NIM NGC API | Zero infra, one line in LiteLLM |
| P3/P4 volume, >3,000 calls/day, own GPU hardware | Self-hosted NIM on Vast.ai | TensorRT-LLM beats Python backend; Vast.ai RTX 3090 at $0.13/hr makes it economical |
| Fine-tuned TinyLlama (v15 adapter), high throughput | vLLM | PagedAttention + LoRA native support; purpose-built for LLMs |
| Embedding model + reranker + LLM on shared A10G | Triton | One server, three models, Prometheus covers all three |
| Preprocessing pipeline + LLM + postprocessing | Triton ensemble | Tensor routing between stages, one HTTP call to client |

For AOIS at current scale: Groq API covers P3/P4. vLLM covers the fine-tuned TinyLlama tier.
Triton becomes the right answer when AOIS grows into a multi-tenant platform serving multiple
teams with mixed model types on shared GPU hardware.

---

## Step 8: AOIS Integration

Triton does not use the OpenAI HTTP protocol — it uses its own inference protocol. LiteLLM
cannot route to raw Triton. The correct approach for AOIS is a direct `tritonclient` adapter
alongside the existing LiteLLM tiers:

```python
# In main.py — add after existing ROUTING_TIERS

import os
import tritonclient.http as httpclient
import numpy as np
import json

TRITON_URL = os.getenv("TRITON_URL", "localhost:8000")
USE_LOCAL_INFERENCE = os.getenv("USE_LOCAL_INFERENCE", "false").lower() == "true"

def call_triton(log_text: str, model_name: str = "aois_tinyllama") -> dict:
    client = httpclient.InferenceServerClient(url=TRITON_URL)
    data = np.array([[log_text.encode("utf-8")]], dtype=object)
    inputs = [httpclient.InferInput("LOG_TEXT", data.shape, "BYTES")]
    inputs[0].set_data_from_numpy(data)
    outputs = [httpclient.InferRequestedOutput("ANALYSIS_JSON")]
    resp = client.infer(model_name=model_name, inputs=inputs, outputs=outputs)
    return json.loads(resp.as_numpy("ANALYSIS_JSON")[0][0].decode("utf-8"))

# Extend ROUTING_TIERS:
ROUTING_TIERS = [
    # ... existing tiers ...
    {
        "name": "triton",
        "condition": lambda severity, _: (
            severity in ["P3", "P4"] and USE_LOCAL_INFERENCE
        ),
        "call": call_triton,
    },
]
```

Test with:
```bash
USE_LOCAL_INFERENCE=true python3 -c "
import asyncio
from main import analyze
result = asyncio.run(analyze('pod OOMKilled exit code 137'))
print(result)
"
# Expected (when Triton is running and USE_LOCAL_INFERENCE=true):
# {'severity': 'P2', 'summary': '...', 'suggested_action': '...', 'confidence': 0.85}
```

Note: if you want LiteLLM to route to Triton, you need an OpenAI-compatible wrapper in front of
Triton. This is exactly what NIM provides: NIM = Triton + OpenAI-compatible HTTP wrapper.

---

## Common Mistakes

### 1. config.pbtxt tensor name mismatch

**Symptom:**
```
tritonclient.utils.InferenceServerException: [StatusCode.INVALID_ARGUMENT]
input 'INPUT_TEXT' does not exist in model 'aois_echo'
```

**Cause:** The tensor name in your client code (`InferInput("INPUT_TEXT", ...)`) does not match
the `name` field in `config.pbtxt`. Names are case-sensitive.

**Fix:** Check `config.pbtxt` exactly:
```bash
grep "name:" /tmp/triton_models/aois_echo/config.pbtxt
# INPUT_TEXT ≠ input_text ≠ Input_Text
```

### 2. Model not detected after directory creation

**Symptom:** `curl localhost:8000/v2/models/new_model/ready` returns 404 after you create the
directory.

**Cause 1:** Triton polls every 5 seconds — wait at least 8 seconds.
**Cause 2:** File permissions — the container cannot read the directory.

**Fix:**
```bash
chmod -R 755 /tmp/triton_models/new_model/
# OR force immediate poll:
curl -X POST localhost:8000/v2/repository/models/new_model/load
# Expected: HTTP 200
```

### 3. initialize() fails silently — model shows UNAVAILABLE

**Symptom:** Triton loads but the model status is `UNAVAILABLE`, no clear error.

**Cause:** An exception in `initialize()` that Triton catches without a clear stack trace at
default verbosity.

**Fix:** Enable verbose logging:
```bash
docker run ... tritonserver --model-repository=/models --log-verbose=3
# Full Python traceback now appears in logs
```

### 4. Dynamic batching not forming batches

**Symptom:** Perf Analyzer at concurrency 8 shows throughput is 8× concurrency-1 — each
request still processes individually.

**Cause:** Requests arrive far apart in time, exceeding `max_queue_delay_microseconds` before
the queue fills. For the echo model, each request completes in <1ms — the queue empties before
the next request arrives.

**Fix:** Increase `max_queue_delay_microseconds` to 50000 (50ms) during testing. For production,
set it to the maximum tolerable latency increase (5ms for low-latency tiers, 50ms for
throughput-first tiers).

### 5. KIND_GPU specified but no GPU in container

**Symptom:**
```
E ... Failed to initialize model instance: no CUDA-capable device is detected
```

**Cause:** Container started without `--gpus all` but `config.pbtxt` specifies `KIND_GPU`.

**Fix:** Either add `--gpus all` to the `docker run` command, or change `config.pbtxt` to
`KIND_CPU` for CPU testing. The two configurations are otherwise identical.

### 6. ensemble_scheduling step order matters

**Symptom:** Ensemble runs but `PIPELINE_OUTPUT` is empty or contains data from the wrong step.

**Cause:** The `output_map` from one step uses a value name that does not match the `input_map`
key in the next step. These are pipeline-internal tensor names — they must match exactly.

**Fix:** Draw the tensor flow on paper first. Each `value` in an `output_map` must appear as
the same `value` in a subsequent `input_map`. No value name can be reused across steps.

---

## Troubleshooting

**Triton container exits on startup:**
```bash
docker logs triton-aois 2>&1 | tail -20
# Look for: "TRITONSERVER_ERROR_INTERNAL: unable to load model"
# Most common cause: malformed config.pbtxt
# Validate: every opening bracket [ or { must have a closing bracket
```

**`tritonclient` import fails:**
```bash
pip install "tritonclient[all]" geventhttpclient
# If geventhttpclient fails on your platform:
pip install "tritonclient[http]" "tritonclient[grpc]"
```

**Model shows READY but inference returns wrong output tensor:**
The output tensor name in `pb_utils.Tensor("OUTPUT_TEXT", ...)` must exactly match the `name`
in the `output` block of `config.pbtxt`. This is the most common Python backend error.

**Perf Analyzer: `Failed to get server metadata`:**
Perf Analyzer must run in a container with network access to Triton. Pass `--net=host` so the
SDK container shares the host network:
```bash
docker run --rm --net=host nvcr.io/nvidia/tritonserver:24.01-py3-sdk \
  perf_analyzer -m aois_echo -u localhost:8000 ...
```

**TinyLlama model.py: `CUDA out of memory`:**
Two causes: (1) `count: 2` in `instance_group` tries to load two model copies — each takes
~2.5GB VRAM, total 5GB. On a 4GB GPU this OOMs. Set `count: 1`. (2) `device_map="cuda:0"` in
the Python backend places the entire model on GPU 0. If another model is already using that GPU,
reduce to `torch_dtype=torch.int8` to halve memory usage.

---

## Connection to Later Phases

**v14 (SGLang, vLLM, Dynamo)**: After this version the comparison is concrete. SGLang beats Triton
Python backend for multi-turn agent LLM serving: RadixAttention reuses shared prefix KV cache
across turns, continuously batches requests, and latency drops on turns 2–3 as the system prompt
hits cache. vLLM beats Triton Python backend for high-concurrency single-turn batch serving
(PagedAttention). Both run on the same Vast.ai instance you just used for Triton. Triton is
correct when you host mixed model types on shared GPU hardware — embedding model, reranker, and
LLM together in a single server.

**v16 (OpenTelemetry)**: Triton exposes Prometheus metrics at `:8002` by default. Add it to
`otel/prometheus.yml` as a scrape target:
```yaml
- job_name: "triton"
  static_configs:
    - targets: ["localhost:8002"]
```
Metrics available: `nv_inference_request_success`, `nv_inference_queue_duration_us`,
`nv_gpu_memory_used_bytes`. These feed directly into the Grafana dashboards built in v16.

**v17 (Kafka)**: When AOIS's Kafka consumer needs to process 1,000 log events per second,
switch from Triton HTTP to gRPC for ~30% lower per-request overhead. `tritonclient.grpc` is
a drop-in replacement for `tritonclient.http`. The gRPC interface is port 8001.

**v20+ (Agents)**: When AOIS gains RAG capabilities (v3.5 pattern), an embedding model runs
alongside the LLM. Triton ensemble handles tokenize → embed → LLM → format as a single server
call. This is the production pattern for RAG at scale: the embedding model and LLM share the
same GPU, served by one Triton instance, without two separate HTTP roundtrips.

**The principle**: NIM, Triton, and vLLM are layers of the same stack. NIM packages Triton.
Triton orchestrates backends. vLLM is a backend that Triton can host via its vLLM backend
plugin. Understanding all three means you can reason about the inference stack from `docker run`
down to the tensor operations — and make the right choice for each scenario rather than
defaulting to whichever you learned first.

---


## Build-It-Blind Challenge

Close the notes. From memory: write a Triton `config.pbtxt` for a Python backend model — correct backend name, input tensor (string, variable length), output tensor (string), instance group with one instance on CPU, max batch size 8. 20 minutes.

```bash
cat model_repository/aois_sre/config.pbtxt
# backend: "python"
# max_batch_size: 8
# input/output tensors defined correctly
```

---

## Failure Injection

Name the backend incorrectly and read the Triton startup error:

```
backend: "Python"   # capital P — wrong
```

Triton is case-sensitive on backend names. The error message tells you exactly what went wrong but only if you know what to look for. Then set `max_batch_size: 0` and observe what changes in throughput behaviour.

---

## Osmosis Check

1. Triton serves the fine-tuned TinyLlama from v15. The LoRA adapter was trained with r=16. If you deploy the base model without the adapter, what changes in output quality — and which v15 eval metric tells you within 10 requests that the adapter is missing?
2. NIM (v13) is built on Triton internally. Name two things NIM adds on top of raw Triton that justify its existence as a separate product. (v13 NIM vs v13.5 Triton comparison)

---

## Mastery Checkpoint

Complete these tasks in sequence. Each depends on the previous.

1. **Explain Triton to a junior engineer in three sentences.** Include: what problem it solves,
   what a backend is, and what a model repository is. No jargon without a one-line definition.

2. **Deploy a working Python backend model** that accepts a `LOG_SEVERITY` string input and
   returns the same string with a `"[AOIS]"` prefix. Verify it with `tritonclient.http`.

3. **Add dynamic batching** to the model above with `preferred_batch_size: [4, 8]` and
   `max_queue_delay_microseconds: 10000`. Run 16 concurrent requests via
   `ThreadPoolExecutor(max_workers=16)` and confirm throughput is higher than 16 sequential
   requests.

4. **Write the config.pbtxt for a two-step ensemble** named `aois_severity_pipeline` that
   chains your `[AOIS]`-prefix model into the uppercase model from Step 4. The config must be
   syntactically correct with a valid `ensemble_scheduling` block. You do not need to run it.

5. **Run Perf Analyzer** against your model at `--concurrency-range 1:8:1`. Record throughput
   and p95 latency at each level. Identify the saturation point.

6. **Deploy TinyLlama on Triton** (GPU required). Export the v15 adapter, write `config.pbtxt`
   and `model.py`, launch Triton with `--gpus all`. Confirm JSON output with a `severity` field
   for three AOIS test logs.

7. **Compare Triton Python backend vs Groq API**: run the same three logs through both, record
   latency and cost. State clearly: at what call volume per day does Triton on a Vast.ai RTX 3090
   ($0.13/hr) become cheaper than Groq ($0.000001/call)? Show your arithmetic.

8. **Add the Triton tier to AOIS** using the `call_triton()` adapter pattern. Route P3/P4 to
   Triton when `USE_LOCAL_INFERENCE=true`. Test with a real log input.

9. **Fill in from memory** (no reference):

| Scenario | NIM, Triton, or vLLM? | One-sentence reason |
|----------|----------------------|---------------------|
| Serve Llama 3.1 8B on NGC hardware, no custom models | ? | ? |
| Serve the v15 TinyLlama LoRA adapter at maximum throughput | ? | ? |
| Shared GPU: embedding model + reranker + LLM on one A10G | ? | ? |
| You own a DGX box and need to serve an NGC-catalog model fast | ? | ? |

**The mastery bar:** You can deploy any HuggingFace model on Triton's Python backend, configure
dynamic batching with a justified delay value, run Perf Analyzer to validate configuration, and
explain to a senior engineer why NIM is faster than your Python backend for the same model —
and under what AOIS scenario that gap does and does not matter.

---

## 4-Layer Tool Understanding

### NVIDIA Triton Inference Server

| Layer | Question | Answer |
|-------|----------|--------|
| **Plain English** | What problem does this solve? | "Lets you run any AI model — not just LLMs — as a network service that multiple applications can call simultaneously, with automatic request queuing and batching built in, and no code changes when you swap one model for another." |
| **System Role** | Where does it sit in AOIS? | Between AOIS's routing layer and GPU hardware. When AOIS routes to a self-hosted model (TinyLlama, an embedding model, a reranker), Triton is the server that hosts it. LiteLLM routes to NIM (which is Triton internally). `tritonclient` calls Triton directly for non-NGC models. |
| **Technical** | What is it, precisely? | A multi-backend inference server that reads a model repository directory, loads each model with the appropriate backend plugin (Python, TensorRT-LLM, ONNX Runtime, vLLM), and serves them via HTTP (8000) and gRPC (8001) with built-in dynamic batching, hot-reload on model changes, and Prometheus metrics at port 8002. |
| **Remove it** | What breaks, and how fast? | AOIS loses its self-hosted inference tier. The fine-tuned TinyLlama from v15 has no server. P3/P4 logs either hit Groq (cost increase per call) or Claude (10× cost). The Prometheus metrics for GPU utilization disappear. Any ensemble pipeline collapses into N separate HTTP calls in application code. |

### Triton Python Backend

| Layer | Question | Answer |
|-------|----------|--------|
| **Plain English** | What problem does this solve? | "Lets you write any Python code — load a PEFT model, run a custom tokenizer, apply business logic — and have Triton serve it the same way it serves a TensorRT or ONNX model." |
| **System Role** | Where does it sit in AOIS? | It is the bridge between Triton's serving infrastructure and the PEFT/transformers model loaded from v15's LoRA adapter. Without the Python backend, Triton cannot serve a LoRA-adapted model — it has no native format for PEFT. |
| **Technical** | What is it, precisely? | A backend plugin that executes a `model.py` file defining `TritonPythonModel` with `initialize()`, `execute(requests)`, and `finalize()` methods. `execute()` receives a list of `InferenceRequest` objects and must return a list of `InferenceResponse` objects of the same length. Communication with the Triton core process happens via shared memory. |
| **Remove it** | What breaks, and how fast? | Triton can only serve TensorRT, ONNX, and PyTorch format models. The TinyLlama LoRA model has no compatible format without the Python backend. AOIS loses the ability to serve custom-adapted models on Triton. Workaround: export the PEFT model to ONNX or compile to TensorRT (hours of work; NVIDIA hardware required). |

### Triton Model Repository

| Layer | Question | Answer |
|-------|----------|--------|
| **Plain English** | What problem does this solve? | "A folder structure that acts as a live menu — drop in a model directory and Triton starts serving it within 5 seconds; remove the directory and Triton stops, all without restarting the server." |
| **System Role** | Where does it sit in AOIS? | It is the configuration surface for Triton. In a production AOIS deployment, the model repository contains `aois_tinyllama/` for the LoRA model and `aois_embedder/` for the embedding model used in RAG. Deploying a new model version is a file copy operation, not a server restart or config change. |
| **Technical** | What is it, precisely? | A filesystem directory where each subdirectory is a model, containing a `config.pbtxt` in Protocol Buffers text format and versioned subdirectories (`1/`, `2/`, `3/`) with the model artifact. Triton polls for changes every 5 seconds and hot-reloads changed models without interrupting requests to unchanged models. |
| **Remove it** | What breaks, and how fast? | Triton cannot start without a model repository path. On a running server, removing a model's directory causes Triton to unload that model within 5 seconds — subsequent requests return HTTP 400 (model not found). There is no gradual degradation: the model is available until the poll cycle detects the missing directory, then it is gone. |
