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


class GeneratedFile(BaseModel):
    """A single generated Java source file."""

    filename: str
    content: str


class GenerateResponse(BaseModel):
    """Structured response containing generated Java code for a design pattern."""

    model_used: str
    pattern: str
    description: str
    files: List[GeneratedFile]
    error: Optional[str] = None


class FollowUpResponse(BaseModel):
    """Structured response for a follow-up question about a pattern analysis."""

    model_used: str
    question: str
    answer: str
    error: Optional[str] = None


class PatternGenerationResult(BaseModel):
    """Result details for a single pattern generation task."""

    pattern: str
    status: str
    files_count: int = 0
    duration_ms: int = 0
    output_zip_relative_path: Optional[str] = None
    error: Optional[str] = None


class BatchGeneratePassProjectsStartResponse(BaseModel):
    """Response returned when a batch generation job is started."""

    job_id: str
    status: str
    total_patterns: int
    output_dir: str


class BatchGeneratePassProjectsStatusResponse(BaseModel):
    """Response containing the current status and progress of a batch generation job."""

    job_id: str
    status: str
    model_used: str
    total_patterns: int
    completed_patterns: int
    successful_patterns: int
    failed_patterns: int
    started_at: float
    updated_at: float
    completed_at: Optional[float] = None
    final_bundle_relative_path: Optional[str] = None
    results: List[PatternGenerationResult]


# ── Batch Metrics Models ───────────────────────────────────────────────────

class MISummary(BaseModel):
    """MI aggregate values extracted from AnalysisSummary for one pattern."""

    avg_mi_score: float
    min_mi_score: float
    max_mi_score: float
    mi_distribution: dict


class CKSummary(BaseModel):
    """CK aggregate values extracted from AnalysisSummary for one pattern.
    None when CK is unavailable (no Java / missing JAR)."""

    ck_overall_score: Optional[float] = None
    avg_wmc: Optional[float] = None
    avg_cbo: Optional[float] = None
    avg_lcom_star: Optional[float] = None
    avg_rfc: Optional[float] = None
    avg_dit: Optional[float] = None
    avg_tcc: Optional[float] = None


class PatternMetricsSummary(BaseModel):
    """Metrics result for a single generated pattern."""

    pattern: str
    status: str          # "success" | "skipped" | "error"
    mi: Optional[MISummary] = None
    ck: Optional[CKSummary] = None
    error: Optional[str] = None


class BatchMetricsResponse(BaseModel):
    """Top-level response for the batch metrics analysis endpoint."""

    title: str
    project_context: str
    job_id: str
    model_used: str
    total_patterns: int
    analyzed_patterns: int
    skipped_patterns: int
    patterns: List[PatternMetricsSummary]
