"""
vLLM inference server on Modal — OpenAI-compatible API.

Serves Mistral-7B-Instruct-v0.3 on a single A10G GPU.
Uses @modal.asgi_app() so vLLM's async engine has full ASGI lifecycle control.

Deploy:  modal deploy vllm_modal/serve.py
Test:    curl https://<endpoint>/health
         curl -X POST https://<endpoint>/v1/chat/completions ...
"""

import modal

MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"
MODEL_REVISION = "e0bc86c23ce5aae1db576c8cca6f06f1f73af2db"
MODEL_DIR = "/models/mistral-7b"

volume = modal.Volume.from_name("aois-model-weights", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.4.3",
        "huggingface_hub",
        "hf_transfer",
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
        import asyncio
        from vllm import AsyncEngineArgs, AsyncLLMEngine
        from vllm.entrypoints.openai.serving_chat import OpenAIServingChat

        engine_args = AsyncEngineArgs(
            model=MODEL_DIR,
            gpu_memory_utilization=0.90,
            max_model_len=8192,
            enforce_eager=False,
        )
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        self.model_config = asyncio.get_event_loop().run_until_complete(
            self.engine.get_model_config()
        )
        self.chat = OpenAIServingChat(
            self.engine,
            self.model_config,
            served_model_names=[MODEL_ID],
            response_role="assistant",
            chat_template=None,
        )

    @modal.asgi_app()
    def serve(self):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, StreamingResponse
        from vllm.entrypoints.openai.protocol import (
            ChatCompletionRequest,
            ErrorResponse,
        )

        fastapi_app = FastAPI(title="AOIS vLLM", version="0.1.0")

        @fastapi_app.get("/health")
        async def health():
            return {"status": "ok", "model": MODEL_ID}

        @fastapi_app.get("/v1/models")
        async def list_models():
            return {
                "object": "list",
                "data": [{"id": MODEL_ID, "object": "model"}],
            }

        @fastapi_app.post("/v1/chat/completions")
        async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
            response = await self.chat.create_chat_completion(request, raw_request)

            if isinstance(response, ErrorResponse):
                return JSONResponse(
                    content=response.model_dump(), status_code=response.code
                )

            if request.stream:
                return StreamingResponse(
                    content=response,
                    media_type="text/event-stream",
                )

            return JSONResponse(content=response.model_dump())

        return fastapi_app


@app.local_entrypoint()
def main():
    """Smoke test: modal run vllm_modal/serve.py"""
    import httpx

    base = "https://kolinzking--aois-vllm-vllmserver-serve.modal.run"
    print(f"Health check: {base}/health")
    r = httpx.get(f"{base}/health", timeout=30)
    print("Status:", r.status_code, r.text)

    print("\nChat completions (cold start may take 3–5 min)...")
    r = httpx.post(
        f"{base}/v1/chat/completions",
        json={
            "model": MODEL_ID,
            "messages": [
                {"role": "system", "content": "You are a helpful SRE assistant."},
                {"role": "user", "content": "In one sentence, what causes OOMKilled in Kubernetes?"},
            ],
            "max_tokens": 128,
            "temperature": 0.1,
        },
        timeout=600,
    )
    print("Status:", r.status_code)
    print("Body:", r.text[:500])
