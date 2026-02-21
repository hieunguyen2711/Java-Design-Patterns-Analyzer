from typing import Dict, List

from config import settings


class Chunker:
    """Chunk Java files into size-limited groups for LLM processing."""

    def __init__(self, max_chars: int | None = None) -> None:
        """Initialize the chunker with a maximum character limit per chunk."""
        self.max_chars = max_chars or settings.MAX_CHARS_PER_CHUNK

    def chunk_files(self, java_files: Dict[str, str]) -> List[Dict[str, str]]:
        """Group Java files into chunks without splitting individual files."""
        chunks: List[Dict[str, str]] = []
        current_chunk: Dict[str, str] = {}
        current_len = 0
        limit = self.max_chars

        for path, content in java_files.items():
            normalized_content = content
            if len(normalized_content) > limit:
                normalized_content = (
                    normalized_content[:limit]
                    + "\n\n[FILE TRUNCATED DUE TO SIZE]"
                )

            file_length = len(normalized_content)
            if current_len + file_length > limit and current_chunk:
                chunks.append(current_chunk)
                current_chunk = {}
                current_len = 0

            current_chunk[path] = normalized_content
            current_len += file_length

        if current_chunk:
            chunks.append(current_chunk)

        return chunks
