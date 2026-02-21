from typing import List

import requests
from fastapi import HTTPException

from config import settings


class OllamaClient:
    """HTTP client for interacting with a local Ollama server."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize the client with an optional custom base URL."""
        self.base_url = base_url or settings.OLLAMA_BASE_URL.rstrip("/")

    def generate(self, prompt: str, model: str) -> str:
        """Generate text from the Ollama model using the provided prompt."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": settings.LLM_TEMPERATURE,
                "num_ctx": settings.NUM_CTX,
            },
        }
        try:
            response = requests.post(url, json=payload, timeout=settings.LLM_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail="Ollama is unreachable. Please ensure the server is running.",
            ) from exc

        if not response.ok:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama returned status {response.status_code}: {response.text}",
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=500, detail="Malformed response from Ollama."
            ) from exc

        if "response" not in data:
            raise HTTPException(
                status_code=500, detail="Missing response content from Ollama."
            )

        return str(data["response"])

    def list_models(self) -> List[str]:
        """Return a list of available models from the Ollama server."""
        url = f"{self.base_url}/api/tags"
        try:
            response = requests.get(url, timeout=5)
            if not response.ok:
                return []
            data = response.json()
            models = data.get("models", [])
            return [model.get("name", "") for model in models if model.get("name")]
        except requests.exceptions.RequestException:
            return []
        except ValueError:
            return []

    def is_running(self) -> bool:
        """Check whether the Ollama server is reachable."""
        try:
            response = requests.get(self.base_url, timeout=3)
            return response.ok
        except requests.exceptions.RequestException:
            return False
