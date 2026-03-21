"""
Pydantic request / response models for the CK + MI metrics endpoint.
"""

from pydantic import BaseModel
from typing import Optional


# ── Request ────────────────────────────────────────────────────────────────

class AnalyzeMetricsRequest(BaseModel):
    project_dir: str
    pattern_name: str = ""


# ── Halstead sub-model ────────────────────────────────────────────────────

class HalsteadMetrics(BaseModel):
    distinct_operators: int
    distinct_operands: int
    total_operators: int
    total_operands: int
    vocabulary: int
    program_length: int
    volume: float
    difficulty: float
    effort: float
    estimated_bugs: float
    estimated_time_seconds: float


# ── Maintainability Index sub-model ───────────────────────────────────────

class MaintainabilityMetrics(BaseModel):
    mi_score: float                    # 0–100
    mi_label: str                      # "Highly Maintainable" etc.
    mi_color: str                      # "green" / "yellow" / "red"
    halstead_volume: float
    cyclomatic_complexity: int
    sloc: int
    halstead: HalsteadMetrics


# ── CK sub-model ──────────────────────────────────────────────────────────

class CKMetrics(BaseModel):
    cbo: int
    wmc: int
    dit: int
    noc: int
    rfc: int
    lcom: float
    lcom_star: float                   # mapped from CK's "lcom*"
    tcc: float
    lcc: float
    loc: int
    total_methods: int
    fanin: int
    fanout: int


# ── Per-class combined result ─────────────────────────────────────────────

class ClassAnalysis(BaseModel):
    class_name: str
    file_path: str
    type: str                          # "class", "interface", "enum"

    # CK metrics — None when CK is unavailable
    ck: Optional[CKMetrics] = None

    # MI metrics — always available (pure Python)
    mi: MaintainabilityMetrics

    # Quality assessment (CK-based)
    ck_scores: Optional[dict[str, str]] = None    # metric → "good"/"moderate"/"concerning"
    ck_overall_score: Optional[float] = None       # 0–100
    flags: list[str] = []
    pattern_notes: list[str] = []


# ── Per-method result (CK only) ──────────────────────────────────────────

class MethodMetrics(BaseModel):
    class_name: str
    method_name: str
    is_constructor: bool
    line: int
    complexity: int                    # cyclomatic complexity
    loc: int
    parameters: int
    max_nesting: int


# ── Summary ───────────────────────────────────────────────────────────────

class AnalysisSummary(BaseModel):
    total_classes: int
    total_methods: int
    total_files: int
    pattern_name: str

    # MI aggregates
    avg_mi_score: float
    min_mi_score: float
    max_mi_score: float
    mi_distribution: dict[str, int]    # {"green": 5, "yellow": 2, "red": 1}

    # CK aggregates — None when CK is unavailable
    avg_wmc: Optional[float] = None
    avg_cbo: Optional[float] = None
    avg_lcom_star: Optional[float] = None
    avg_tcc: Optional[float] = None
    avg_rfc: Optional[float] = None
    avg_dit: Optional[float] = None
    ck_overall_score: Optional[float] = None

    # Halstead aggregates
    avg_halstead_volume: float
    avg_halstead_difficulty: float
    total_estimated_bugs: float
    avg_sloc: float


# ── Top-level response ────────────────────────────────────────────────────

class AnalyzeMetricsResponse(BaseModel):
    summary: AnalysisSummary
    classes: list[ClassAnalysis]
    methods: list[MethodMetrics]       # empty list when CK is unavailable


# ── PIQS models ───────────────────────────────────────────────────────────

class PIQSPropertyAssessment(BaseModel):
    property_id: str
    weight: int
    satisfaction: int
    justification: str


class PIQSFormulaResult(BaseModel):
    formula: str
    result_percent: float


class PIQSResponse(BaseModel):
    pattern_name: str
    files_analyzed: list[str]
    base_predicates: dict[str, bool]
    derived_predicates: dict[str, bool]
    logical_assessment: list[PIQSPropertyAssessment]
    breadth_calculation_psr: PIQSFormulaResult
    depth_calculation_cpc: PIQSFormulaResult
    final_quality_result_piqs: PIQSFormulaResult
    grade: str
