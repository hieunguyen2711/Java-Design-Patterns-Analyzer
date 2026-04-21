from typing import List

from pydantic import BaseModel, Field


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


class GeneratedFileInput(BaseModel):
    """A single Java file to include in the packaged project."""

    filename: str
    content: str


class PackageProjectRequest(BaseModel):
    """Request model for packaging generated Java files into a downloadable project zip."""

    pattern: str
    description: str
    files: List[GeneratedFileInput]


class BatchGeneratePassProjectsRequest(BaseModel):
    """Request model to generate projects for all passing patterns using one shared project context."""

    project_context: str = Field(min_length=1)
    model: str = "qwen3-coder-30b-a3b-instruct"
    concurrency: int = Field(default=1, ge=1, le=8)
    patterns_limit: int | None = Field(default=None, ge=1)