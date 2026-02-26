from pydantic import BaseModel


class AnalyzeZipRequest(BaseModel):
    """Request model for analyzing a zipped Java project."""

    model: str = "qwen3-coder-30b-a3b-instruct"


class AnalyzeFolderRequest(BaseModel):
    """Request model for analyzing uploaded Java source files."""

    model: str = "qwen3-coder-30b-a3b-instruct"


class GenerateRequest(BaseModel):
    """Request model for generating Java code that follows a design pattern."""

    pattern: str
    description: str
    model: str = "qwen3-coder-30b-a3b-instruct"


class FollowUpRequest(BaseModel):
    """Request model for asking a follow-up question about a prior pattern analysis."""

    analysis: str
    question: str
    model: str = "qwen3-coder-30b-a3b-instruct"
