from fastapi import APIRouter

from llm.client import OllamaClient

router = APIRouter()

ollama_client = OllamaClient()


@router.get("/models")
def list_models():
    """Return available Ollama models."""
    return {"models": ollama_client.list_models()}
