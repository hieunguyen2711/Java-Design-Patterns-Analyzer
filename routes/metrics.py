"""
FastAPI router for the CK + Maintainability Index analysis endpoint.

POST /api/v1/analyze-metrics
"""

import os

from fastapi import APIRouter, HTTPException

from models.metrics import AnalyzeMetricsRequest, AnalyzeMetricsResponse
from services.analysis_pipeline import analyze_project_async

router = APIRouter(prefix="/api/v1", tags=["metrics"])


@router.post("/analyze-metrics", response_model=AnalyzeMetricsResponse)
async def analyze_metrics(req: AnalyzeMetricsRequest):
    """Run CK + MI metrics on generated Java code.

    - **MI** is always computed (pure Python, no external deps).
    - **CK** is computed when Java + CK JAR are available; otherwise
      the response contains MI-only data with CK fields set to ``null``.
    """

    if not os.path.isdir(req.project_dir):
        raise HTTPException(
            status_code=400,
            detail=f"Directory not found: {req.project_dir}",
        )

    # Check that the directory contains at least one .java file
    java_files: list[str] = []
    for root, _, files in os.walk(req.project_dir):
        java_files.extend(f for f in files if f.endswith(".java"))
    if not java_files:
        raise HTTPException(
            status_code=422,
            detail="No .java files found in project directory",
        )

    try:
        result = await analyze_project_async(req.project_dir, req.pattern_name)
        return AnalyzeMetricsResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
