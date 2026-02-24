from typing import Set

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or defaults."""

    OLLAMA_BASE_URL: str = "http://127.0.0.1:1234"
    DEFAULT_MODEL: str = "qwen3-coder-30b-a3b-instruct"
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT: int = 300
    NUM_CTX: int = 4096
    MAX_FILE_SIZE_MB: int = 50
    MAX_JAVA_FILES: int = 150
    MAX_CHARS_PER_CHUNK: int = 8000
    MAX_MERGE_CHARS: int = 6000  # cap merged partial results sent to LLM
    UPLOAD_DIR: str = "temp_uploads"
    SKIP_DIRS: Set[str] = {
        ".git",
        "target",
        "build",
        ".idea",
        "node_modules",
        "__pycache__",
        ".gradle",
        ".mvn",
        "out",
        "bin",
        "dist",
    }


settings = Settings()
