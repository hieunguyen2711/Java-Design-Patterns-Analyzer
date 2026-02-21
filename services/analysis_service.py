from typing import Dict, List

from llm.client import OllamaClient
from llm.chunker import Chunker
from models.response_models import AnalysisResponse
from services.file_service import FileService
from services.prompt_service import PromptService
from utils import validators


class AnalysisService:
    """Coordinate validation, prompt construction, LLM calls, and response assembly."""

    def __init__(
        self,
        file_service: FileService | None = None,
        chunker: Chunker | None = None,
        prompt_service: PromptService | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        """Initialize service dependencies with defaults when not provided."""
        self.file_service = file_service or FileService()
        self.chunker = chunker or Chunker()
        self.prompt_service = prompt_service or PromptService()
        self.ollama_client = ollama_client or OllamaClient()

    def analyze(self, java_files: Dict[str, str], model: str) -> AnalysisResponse:
        """Run the end-to-end analysis flow and return a structured response."""
        validators.validate_files(java_files)

        folder_tree = self.file_service.build_folder_tree(java_files)
        chunks = self.chunker.chunk_files(java_files)

        partial_results: List[str] = []
        for idx, chunk in enumerate(chunks):
            prompt = self.prompt_service.build_chunk_prompt(
                chunk, idx, len(chunks)
            )
            result = self.ollama_client.generate(prompt, model)
            partial_results.append(result)

        if len(chunks) > 1:
            merge_prompt = self.prompt_service.build_merge_prompt(partial_results)
            final_analysis = self.ollama_client.generate(merge_prompt, model)
        else:
            final_analysis = partial_results[0]

        return AnalysisResponse(
            model_used=model,
            file_count=len(java_files),
            files_analyzed=list(java_files.keys()),
            folder_structure=folder_tree,
            raw_analysis=final_analysis,
            chunks_used=len(chunks),
            error=None,
        )
