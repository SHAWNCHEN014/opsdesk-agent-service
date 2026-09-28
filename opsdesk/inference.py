import time

import httpx


class InferenceGateway:
    def __init__(self, config):
        self.config = config
        self.calls = []

    async def ask(self, purpose, instructions, payload, schema=None):
        if self.config.model_mode != "ollama":
            raise RuntimeError("No real model selected")
        started = time.monotonic()
        record = {"purpose": purpose, "provider": "ollama", "model": self.config.model_name}
        body = {"model": self.config.model_name, "stream": False, "think": False,
                "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": payload}],
                "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 512 if schema is None else 240}}
        if schema is not None:
            body["format"] = schema.model_json_schema()
        try:
            async with httpx.AsyncClient(timeout=self.config.model_timeout) as client:
                response = await client.post(self.config.ollama_url.rstrip("/") + "/api/chat", json=body)
                response.raise_for_status()
                result = response.json()
            record.update(success=True, input_tokens=result.get("prompt_eval_count"), output_tokens=result.get("eval_count"))
            text = result["message"]["content"].strip()
            return schema.model_validate_json(text) if schema is not None else text
        except Exception as exc:
            record.update(success=False, error=type(exc).__name__)
            raise
        finally:
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            self.calls.append(record)


async def embed(config, texts):
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(config.ollama_url.rstrip("/") + "/api/embed", json={"model": config.embed_model, "input": texts})
        response.raise_for_status()
        values = response.json()["embeddings"]
        if len(values) != len(texts):
            raise ValueError("Embedding batch size mismatch")
        return values


async def embedding_identity(config):
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(config.ollama_url.rstrip("/") + "/api/tags")
        response.raise_for_status()
    for model in response.json().get("models", []):
        if model.get("name", "").removesuffix(":latest") == config.embed_model.removesuffix(":latest"):
            return config.embed_model + ":" + model["digest"]
    raise ValueError("Configured embedding model is not installed")
