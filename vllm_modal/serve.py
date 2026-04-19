"""
vLLM inference server on Modal — OpenAI-compatible API.

Serves Mistral-7B-Instruct-v0.3 on a single A10G GPU.
LiteLLM routes to this via the openai/ prefix pointing at the Modal endpoint.

Deploy:  modal deploy vllm_modal/serve.py
Run:     modal run vllm_modal/serve.py
"""

import modal

# Modal image: vLLM + HuggingFace hub
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.4.3",
        "huggingface_hub",
        "hf_transfer",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App("aois-vllm", image=image)

MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"
MODEL_REVISION = "e0bc86c23ce5aae1db576c8cca6f06f1f73af2db"  # pinned — no `latest`


@app.cls(
    gpu="a10g",
    container_idle_timeout=300,
    max_inputs=32,
)
class VLLMServer:
    @modal.build()
    def build(self):
        """Download model weights at build time — baked into the container image."""
        from huggingface_hub import snapshot_download
        snapshot_download(
            MODEL_ID,
            revision=MODEL_REVISION,
            ignore_patterns=["*.pt", "*.gguf"],  # skip non-safetensors weights
        )

    @modal.enter()
    def load(self):
        """Start vLLM engine when the container enters (before first request)."""
        from vllm import AsyncEngineArgs, AsyncLLMEngine
        engine_args = AsyncEngineArgs(
            model=MODEL_ID,
            revision=MODEL_REVISION,
            gpu_memory_utilization=0.90,
            max_model_len=8192,
            enforce_eager=False,
        )
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)

    @modal.web_endpoint(method="POST", docs=True)
    async def v1_chat_completions(self, request: dict) -> dict:
        """OpenAI-compatible /v1/chat/completions endpoint."""
        from vllm import SamplingParams
        from vllm.utils import random_uuid

        messages = request.get("messages", [])
        max_tokens = request.get("max_tokens", 1024)
        temperature = request.get("temperature", 0.1)

        prompt = _apply_chat_template(messages)

        sampling_params = SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
            stop=["</s>", "[INST]"],
        )

        request_id = random_uuid()
        results_generator = self.engine.generate(prompt, sampling_params, request_id)

        final_output = None
        async for request_output in results_generator:
            final_output = request_output

        text = final_output.outputs[0].text
        prompt_tokens = len(final_output.prompt_token_ids)
        completion_tokens = len(final_output.outputs[0].token_ids)

        return {
            "id": f"cmpl-{request_id}",
            "object": "chat.completion",
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": final_output.outputs[0].finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


def _apply_chat_template(messages: list[dict]) -> str:
    """Mistral instruct format: [INST] user [/INST] assistant </s>"""
    prompt = ""
    system = ""

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "system":
            system = content
        elif role == "user":
            user_content = f"{system}\n\n{content}" if system else content
            prompt += f"[INST] {user_content} [/INST]"
            system = ""
        elif role == "assistant":
            prompt += f" {content}</s>"

    return prompt


@app.local_entrypoint()
def main():
    """Quick smoke test: run `modal run vllm_modal/serve.py`"""
    server = VLLMServer()
    response = server.v1_chat_completions.remote({
        "messages": [
            {"role": "system", "content": "You are a helpful SRE assistant."},
            {"role": "user", "content": "In one sentence, what causes OOMKilled in Kubernetes?"},
        ],
        "max_tokens": 128,
        "temperature": 0.1,
    })
    print("\n--- vLLM response ---")
    print(response["choices"][0]["message"]["content"])
    usage = response["usage"]
    print(f"Tokens: {usage['prompt_tokens']} prompt + {usage['completion_tokens']} completion")
