import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyze_router, metrics_router, models_router
from app.core import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
from app.llm.client import OllamaClient


app = FastAPI(title="Java Design Pattern Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(models_router)
app.include_router(metrics_router)


@app.on_event("startup")
def startup_event() -> None:
    """Print startup information including Ollama status and default model."""
    ollama = OllamaClient()
    status = "RUNNING" if ollama.is_running() else "NOT RUNNING"
    print("Backend running at http://localhost:8000")
    print(f"Ollama status: {status}")
    print(f"Default model: {settings.DEFAULT_MODEL}")
