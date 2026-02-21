from pydantic import BaseModel


class AnalyzeZipRequest(BaseModel):
    """Request model for analyzing a zipped Java project."""

    model: str = "qwen3-coder-30b-a3b-instruct"


class AnalyzeFolderRequest(BaseModel):
    """Request model for analyzing uploaded Java source files."""

    model: str = "qwen3-coder-30b-a3b-instruct"
