from __future__ import annotations

import base64
from typing import Any, cast

import httpx

from hermes.auth import outbound_service_auth_enabled, serverless_identity_headers


def _object(response: httpx.Response) -> dict[str, Any]:
    payload = cast(Any, response.json())
    if not isinstance(payload, dict):
        raise ValueError("multimodal gateway response must be a JSON object")
    return cast(dict[str, Any], payload)


class OpenAICompatibleMultimodal:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        *,
        service_audience: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.service_audience = service_audience

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if outbound_service_auth_enabled() and self.service_audience:
            headers.update(serverless_identity_headers(self.service_audience))
        return headers

    async def embed(self, *, model: str, inputs: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/embeddings",
                headers=self._headers(),
                json={"model": model, "input": inputs},
            )
            response.raise_for_status()
            data = _object(response).get("data")
        if not isinstance(data, list):
            raise ValueError("embedding gateway returned invalid data")
        vectors: list[list[float]] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise ValueError("embedding gateway returned invalid vector")
            vector = item["embedding"]
            if not all(isinstance(value, int | float) for value in vector):
                raise ValueError("embedding vector must be numeric")
            vectors.append([float(value) for value in vector])
        return vectors

    async def vision(self, *, model: str, prompt: str, image_url: str) -> str:
        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions", headers=self._headers(), json=body
            )
            response.raise_for_status()
            payload = _object(response)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("vision gateway returned no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("vision gateway returned invalid content")
        return cast(str, message["content"])

    async def transcribe(self, *, model: str, audio: bytes, filename: str = "audio.bin") -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/audio/transcriptions",
                headers=self._headers(),
                data={"model": model},
                files={"file": (filename, audio)},
            )
            response.raise_for_status()
            payload = _object(response)
        text = payload.get("text")
        if not isinstance(text, str):
            raise ValueError("transcription gateway returned invalid text")
        return text

    async def speech(self, *, model: str, voice: str, text: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/audio/speech",
                headers=self._headers(),
                json={"model": model, "voice": voice, "input": text},
            )
            response.raise_for_status()
            return base64.b64encode(response.content).decode("ascii")

    async def rerank(self, *, model: str, query: str, documents: list[str]) -> list[float]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/rerank",
                headers=self._headers(),
                json={"model": model, "query": query, "documents": documents},
            )
            response.raise_for_status()
            payload = _object(response)
        results = payload.get("results")
        if not isinstance(results, list):
            raise ValueError("rerank gateway returned invalid results")
        scores: list[float] = []
        for item in results:
            if not isinstance(item, dict) or not isinstance(item.get("relevance_score"), int | float):
                raise ValueError("rerank result missing relevance_score")
            scores.append(float(item["relevance_score"]))
        return scores
