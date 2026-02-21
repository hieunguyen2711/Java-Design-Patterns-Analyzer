from typing import List, Optional

from pydantic import BaseModel


class AnalysisResponse(BaseModel):
    """Structured response containing the design pattern analysis results."""

    model_used: str
    file_count: int
    files_analyzed: List[str]
    folder_structure: dict
    raw_analysis: str
    chunks_used: int
    error: Optional[str] = None
