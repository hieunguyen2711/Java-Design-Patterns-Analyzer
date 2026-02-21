from typing import List

import requests
from fastapi import HTTPException

from config import settings


class OllamaClient:
    """HTTP client for interacting with a local LM Studio server (OpenAI-compatible API)."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize the client with an optional custom base URL."""
        self.base_url = base_url or settings.OLLAMA_BASE_URL.rstrip("/")

    def generate(self, prompt: str, model: str) -> str:
        """Generate text from the LM Studio model using the OpenAI-compatible chat endpoint."""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.NUM_CTX,
        }
        try:
            response = requests.post(url, json=payload, timeout=settings.LLM_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail="LM Studio is unreachable. Please ensure the server is running.",
            ) from exc

        if not response.ok:
            raise HTTPException(
                status_code=502,
                detail=f"LM Studio returned status {response.status_code}: {response.text}",
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=500, detail="Malformed response from LM Studio."
            ) from exc

        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError) as exc:
            raise HTTPException(
                status_code=500, detail="Missing response content from LM Studio."
            ) from exc

    def list_models(self) -> List[str]:
        """Return a list of available models from the LM Studio server."""
        url = f"{self.base_url}/v1/models"
        try:
            response = requests.get(url, timeout=5)
            if not response.ok:
                return []
            data = response.json()
            models = data.get("data", [])
            return [m.get("id", "") for m in models if m.get("id")]
        except requests.exceptions.RequestException:
            return []
        except ValueError:
            return []

    def is_running(self) -> bool:
        """Check whether the LM Studio server is reachable."""
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=3)
            return response.ok
        except requests.exceptions.RequestException:
            return False
