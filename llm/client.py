import logging
from typing import List

import requests
from fastapi import HTTPException

from config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """HTTP client for interacting with a local LM Studio server (OpenAI-compatible API)."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize the client with an optional custom base URL."""
        self.use_open_router = settings.USE_OPEN_ROUTER
        resolved_base = settings.OPEN_ROUTER_BASE_URL if self.use_open_router else settings.OLLAMA_BASE_URL
        self.base_url = (base_url or resolved_base).rstrip("/")

    def _request_headers(self) -> dict[str, str]:
        """Build provider-specific request headers."""
        if not self.use_open_router:
            return {}
        if not settings.OPEN_ROUTER_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="USE_OPEN_ROUTER is enabled but OPEN_ROUTER_API_KEY is missing.",
            )

        return {
            "Authorization": f"Bearer {settings.OPEN_ROUTER_API_KEY}",
            "HTTP-Referer": settings.OPEN_ROUTER_SITE_URL,
            "X-Title": settings.OPEN_ROUTER_APP_NAME,
        }

    def generate(self, prompt: str, model: str) -> str:
        """Generate text from the LM Studio model using the OpenAI-compatible chat endpoint."""
        url = f"{self.base_url}/v1/chat/completions"
        provider = "OpenRouter" if self.use_open_router else "LM Studio"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.MAX_OUTPUT_TOKENS,
        }
        logger.info("Sending request to %s: model=%s, prompt_chars=%d", provider, model, len(prompt))
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._request_headers(),
                timeout=settings.LLM_TIMEOUT,
            )
        except requests.exceptions.Timeout as exc:
            logger.error("%s request timed out after %ds (model=%s, prompt_chars=%d)", provider, settings.LLM_TIMEOUT, model, len(prompt))
            raise HTTPException(
                status_code=502,
                detail=(
                    f"{provider} timed out after {settings.LLM_TIMEOUT}s. "
                    "Try a smaller file set, lower MAX_OUTPUT_TOKENS, or increase LLM_TIMEOUT."
                ),
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.error("%s connection error: %s", provider, exc)
            raise HTTPException(
                status_code=502,
                detail=f"{provider} is unreachable. Please ensure the service is running.",
            ) from exc

        if not response.ok:
            logger.error("%s returned HTTP %d: %s", provider, response.status_code, response.text[:500])
            raise HTTPException(
                status_code=502,
                detail=f"{provider} returned status {response.status_code}: {response.text}",
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
            response = requests.get(url, headers=self._request_headers(), timeout=5)
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
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers=self._request_headers(),
                timeout=3,
            )
            return response.ok
        except requests.exceptions.RequestException:
            return False
