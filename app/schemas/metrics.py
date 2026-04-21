"""
Pydantic request / response models for the CK + MI metrics endpoint.
"""

from typing import Optional

from pydantic import BaseModel


class AnalyzeMetricsRequest(BaseModel):
    project_dir: str
    pattern_name: str = ""


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


class MaintainabilityMetrics(BaseModel):
    mi_score: float
    mi_label: str
    mi_color: str
    halstead_volume: float
    cyclomatic_complexity: int
    sloc: int
    halstead: HalsteadMetrics


class CKMetrics(BaseModel):
    cbo: int
    wmc: int
    dit: int
    noc: int
    rfc: int
    lcom: float
    lcom_star: float
    tcc: float
    lcc: float
    loc: int
    total_methods: int
    fanin: int
    fanout: int


class ClassAnalysis(BaseModel):
    class_name: str
    file_path: str
    type: str
    ck: Optional[CKMetrics] = None
    mi: MaintainabilityMetrics
    ck_scores: Optional[dict[str, str]] = None
    ck_overall_score: Optional[float] = None
    flags: list[str] = []
    pattern_notes: list[str] = []


class MethodMetrics(BaseModel):
    class_name: str
    method_name: str
    is_constructor: bool
    line: int
    complexity: int
    loc: int
    parameters: int
    max_nesting: int


class AnalysisSummary(BaseModel):
    total_classes: int
    total_methods: int
    total_files: int
    pattern_name: str
    avg_mi_score: float
    min_mi_score: float
    max_mi_score: float
    mi_distribution: dict[str, int]
    avg_wmc: Optional[float] = None
    avg_cbo: Optional[float] = None
    avg_lcom_star: Optional[float] = None
    avg_tcc: Optional[float] = None
    avg_rfc: Optional[float] = None
    avg_dit: Optional[float] = None
    ck_overall_score: Optional[float] = None
    ck_q_score: Optional[float] = None
    cqs_score: Optional[float] = None
    avg_halstead_volume: float
    avg_halstead_difficulty: float
    total_estimated_bugs: float
    avg_sloc: float


class AnalyzeMetricsResponse(BaseModel):
    summary: AnalysisSummary
    classes: list[ClassAnalysis]
    methods: list[MethodMetrics]


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