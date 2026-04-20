"""
vLLM inference server on Modal — OpenAI-compatible API.

Serves Mistral-7B-Instruct-v0.3 on a single A10G GPU.

Pattern: vLLM's built-in OpenAI server runs as a subprocess on port 8000.
The @modal.asgi_app() proxies all requests to it — version-agnostic and clean.

Deploy:  modal deploy vllm_modal/serve.py
Test:    curl https://<endpoint>/health
"""

import modal

MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"
MODEL_REVISION = "e0bc86c23ce5aae1db576c8cca6f06f1f73af2db"
MODEL_DIR = "/models/mistral-7b"
VLLM_PORT = 8000

volume = modal.Volume.from_name("aois-model-weights", create_if_missing=True)

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.0-devel-ubuntu22.04",
        add_python="3.11",
    )
    .pip_install(
        "vllm==0.7.3",
        "huggingface_hub",
        "hf_transfer",
        "httpx",
        "fastapi",
        "uvicorn",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App("aois-vllm", image=image)


@app.function(volumes={MODEL_DIR: volume}, timeout=3600)
def download_model():
    """Download model weights into the persistent volume. Run once."""
    import os
    from huggingface_hub import snapshot_download

    if os.path.exists(f"{MODEL_DIR}/config.json"):
        print("Model already downloaded — skipping.")
        return

    print(f"Downloading {MODEL_ID}...")
    snapshot_download(
        MODEL_ID,
        revision=MODEL_REVISION,
        local_dir=MODEL_DIR,
        ignore_patterns=["*.pt", "*.gguf"],
    )
    volume.commit()
    print("Done.")


@app.cls(
    gpu="a10g",
    scaledown_window=300,
    startup_timeout=600,
    volumes={MODEL_DIR: volume},
)
@modal.concurrent(max_inputs=32)
class VLLMServer:
    @modal.enter()
    def load(self):
        import subprocess
        import time
        import httpx

        self.proc = subprocess.Popen(
            [
                "python3", "-m", "vllm.entrypoints.openai.api_server",
                "--model", MODEL_DIR,
                "--served-model-name", MODEL_ID,
                "--host", "127.0.0.1",
                "--port", str(VLLM_PORT),
                "--gpu-memory-utilization", "0.90",
                "--max-model-len", "8192",
                # Mistral fast tokenizer (TokenizersBackend) missing all_special_tokens_extended.
                # Slow mode uses Python tokenizer, avoids the Rust backend entirely.
                "--tokenizer-mode", "slow",
            ]
        )

        print("Waiting for vLLM server to be ready (model loading)...")
        client = httpx.Client()
        for attempt in range(120):  # 10 minutes max
            try:
                r = client.get(f"http://127.0.0.1:{VLLM_PORT}/health", timeout=5)
                if r.status_code == 200:
                    print(f"vLLM server ready after {attempt * 5}s")
                    break
            except Exception:
                pass
            time.sleep(5)
        else:
            self.proc.kill()
            raise RuntimeError("vLLM server failed to start within 10 minutes")

        self.http_client = httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{VLLM_PORT}",
            timeout=300,
        )

    @modal.asgi_app()
    def serve(self):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, StreamingResponse, Response

        fastapi_app = FastAPI(title="AOIS vLLM", version="0.1.0")
        client = self.http_client

        @fastapi_app.api_route("/{path:path}", methods=["GET", "POST", "DELETE"])
        async def proxy(path: str, request: Request):
            body = await request.body()
            headers = {
                k: v for k, v in request.headers.items()
                if k.lower() not in ("host", "content-length")
            }

            upstream = await client.request(
                method=request.method,
                url=f"/{path}",
                content=body,
                headers=headers,
            )

            content_type = upstream.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                return StreamingResponse(
                    upstream.aiter_bytes(),
                    media_type="text/event-stream",
                    status_code=upstream.status_code,
                )

            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                media_type=content_type,
            )

        return fastapi_app


@app.local_entrypoint()
def main():
    """Smoke test: modal run vllm_modal/serve.py"""
    import httpx

    base = "https://kolinzking--aois-vllm-vllmserver-serve.modal.run"
    print(f"Health: GET {base}/health")
    r = httpx.get(f"{base}/health", timeout=60)
    print("Status:", r.status_code, r.text)

    if r.status_code != 200:
        print("Server not healthy — aborting.")
        return

    print("\nChat (cold start may take 3–5 min first time)...")
    r = httpx.post(
        f"{base}/v1/chat/completions",
        json={
            "model": MODEL_ID,
            "messages": [
                {"role": "system", "content": "You are a helpful SRE assistant."},
                {"role": "user", "content": "In one sentence, what causes OOMKilled?"},
            ],
            "max_tokens": 128,
            "temperature": 0.1,
        },
        timeout=600,
    )
    print("Status:", r.status_code)
    print("Body:", r.text[:500])
